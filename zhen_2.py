import time
import json
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import TimedRotatingFileHandler
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import okx.Account_api as AccountAPI
import pandas as pd

# 读取配置文件
with open('config.json', 'r') as f:
    config = json.load(f)

# 提取配置
okx_config = config['okx']
trading_pairs_config = config.get('tradingPairs', {})
monitor_interval = config.get('monitor_interval', 60)  # 默认60秒
feishu_webhook = config.get('feishu_webhook', '')
leverage_value = config.get('leverage', 10)

trade_api = TradeAPI.TradeAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
market_api = MarketAPI.MarketAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
public_api = PublicAPI.PublicAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
account_api = AccountAPI.AccountAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')

log_file = "log/okx2.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
file_handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

instrument_info_dict = {}

def fetch_and_store_all_instruments(instType='SWAP'):
    try:
        logger.info(f"Fetching all instruments for type: {instType}")
        response = public_api.get_instruments(instType=instType)
        if 'data' in response and len(response['data']) > 0:
            instrument_info_dict.clear()
            for instrument in response['data']:
                instId = instrument['instId']
                instrument_info_dict[instId] = instrument
                logger.info(f"Stored instrument: {instId}")
        else:
            raise ValueError("Unexpected response structure or no instrument data available")
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        raise

def send_feishu_notification(message):
    if feishu_webhook:
        headers = {'Content-Type': 'application/json'}
        data = {"msg_type": "text", "content": {"text": message}}
        response = requests.post(feishu_webhook, headers=headers, json=data)
        if response.status_code == 200:
            logger.info("飞书通知发送成功")
        else:
            logger.error(f"飞书通知发送失败: {response.text}")

def get_mark_price(instId):
    response = market_api.get_ticker(instId)
    if 'data' in response and len(response['data']) > 0:
        last_price = response['data'][0]['last']
        return float(last_price)
    else:
        raise ValueError("Unexpected response structure or missing 'last' key")

def round_price_to_tick(price, tick_size):
    # 计算 tick_size 的小数位数
    tick_decimals = len(f"{tick_size:.10f}".rstrip('0').split('.')[1]) if '.' in f"{tick_size:.10f}" else 0

    # 调整价格为 tick_size 的整数倍
    adjusted_price = round(price / tick_size) * tick_size
    return f"{adjusted_price:.{tick_decimals}f}"

def get_historical_klines(instId, bar='1m', limit=241):
    response = market_api.get_candlesticks(instId, bar=bar, limit=limit)
    if 'data' in response and len(response['data']) > 0:
        return response['data']
    else:
        raise ValueError("Unexpected response structure or missing candlestick data")

def calculate_atr(klines, period=60):
    trs = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return atr

def calculate_ema_pandas(data, period):
    """
    使用 pandas 计算 EMA
    :param 收盘价列表
    :param period: EMA 周期
    :return: EMA 值
    """
    df = pd.Series(data)
    ema = df.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]  # 返回最后一个 EMA 值


def calculate_average_amplitude(klines, period=60):
    amplitudes = []
    for i in range(len(klines) - period, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        close = float(klines[i][4])
        amplitude = ((high - low) / close) * 100
        amplitudes.append(amplitude)
    average_amplitude = sum(amplitudes) / len(amplitudes)
    return average_amplitude

def cancel_all_orders(instId):
    open_orders = trade_api.get_order_list(instId=instId, state='live')
    order_ids = [order['ordId'] for order in open_orders['data']]
    for ord_id in order_ids:
        trade_api.cancel_order(instId=instId, ordId=ord_id)
    logger.info(f"{instId}挂单取消成功.")

def set_leverage(instId, leverage, mgnMode='isolated', posSide=None):
    try:
        body = {
            "instId": instId,
            "lever": str(leverage),
            "mgnMode": mgnMode
        }
        if mgnMode == 'isolated' and posSide:
            body["posSide"] = posSide
        response = account_api.set_leverage(**body)
        if response['code'] == '0':
            logger.info(f"Leverage set to {leverage}x for {instId} with mgnMode: {mgnMode}")
        else:
            logger.error(f"Failed to set leverage: {response['msg']}")
    except Exception as e:
        logger.error(f"Error setting leverage: {e}")

def place_order(instId, price, amount_usdt, side):
    if instId not in instrument_info_dict:
        logger.error(f"Instrument {instId} not found in instrument info dictionary")
        return
    tick_size = float(instrument_info_dict[instId]['tickSz'])
    adjusted_price = round_price_to_tick(price, tick_size)

    response = public_api.convert_contract_coin(type='1', instId=instId, sz=str(amount_usdt), px=str(adjusted_price), unit='usdt', opType='open')
    if response['code'] == '0':
        sz = response['data'][0]['sz']
        if float(sz) > 0:

            pos_side = 'long' if side == 'buy' else 'short'
            set_leverage(instId, leverage_value, mgnMode='isolated', posSide=pos_side)
            order_result = trade_api.place_order(
                instId=instId,
                tdMode='isolated',
                posSide=pos_side,
                side=side,
                ordType='limit',
                sz=sz,
                px=str(adjusted_price)
            )
            logger.info(f"Order placed: {order_result}")
        else:
            logger.info(f"{instId}计算出的合约张数太小，无法下单。")
    else:
        logger.info(f"{instId}转换失败: {response['msg']}")
        send_feishu_notification(f"{instId}转换失败: {response['msg']}")

def process_pair(instId, pair_config):
    try:
        mark_price = get_mark_price(instId)
        klines = get_historical_klines(instId)

        # 提取收盘价数据用于计算 EMA
        close_prices = [float(kline[4]) for kline in klines[::-1]]  # K线中的收盘价，顺序要新的在最后

        # 计算 EMA
        ema_value = pair_config.get('ema', 240)
        # 如果ema值为0 不区分方向，两头都挂单
        if ema_value == 0:
            is_bullish_trend = True
            is_bearish_trend = True
        else:
            ema60 = calculate_ema_pandas(close_prices, period=ema_value)
            logger.info(f"{instId} EMA60: {ema60:.6f}, 当前价格: {mark_price:.6f}")
            # 判断趋势：多头趋势或空头趋势
            is_bullish_trend = close_prices[-1] > ema60  # 收盘价在 EMA60 之上
            is_bearish_trend = close_prices[-1] < ema60  # 收盘价在 EMA60 之下

        # 计算 ATR
        atr = calculate_atr(klines)
        price_atr_ratio = (mark_price / atr) / 100
        logger.info(f"{instId} ATR: {atr}, 当前价格/ATR比值: {price_atr_ratio:.3f}")

        average_amplitude = calculate_average_amplitude(klines)
        logger.info(f"{instId} ATR: {atr}, 平均振幅: {average_amplitude:.2f}%")

        value_multiplier = pair_config.get('value_multiplier', 2)
        selected_value = (average_amplitude + price_atr_ratio)/2 * value_multiplier

        long_price_factor = 1 - selected_value / 100
        short_price_factor = 1 + selected_value / 100

        long_amount_usdt = pair_config.get('long_amount_usdt', 20)
        short_amount_usdt = pair_config.get('short_amount_usdt', 20)

        target_price_long = mark_price * long_price_factor
        target_price_short = mark_price * short_price_factor

        logger.info(f"{instId} Long target price: {target_price_long:.6f}, Short target price: {target_price_short:.6f}")

        cancel_all_orders(instId)

        # 判断趋势后决定是否挂单
        if is_bullish_trend:
            logger.info(f"{instId} 当前为多头趋势，允许挂多单")
            place_order(instId, target_price_long, long_amount_usdt, 'buy')
        else:
            logger.info(f"{instId} 当前非多头趋势，跳过多单挂单")

        if is_bearish_trend:
            logger.info(f"{instId} 当前为空头趋势，允许挂空单")
            place_order(instId, target_price_short, short_amount_usdt, 'sell')
        else:
            logger.info(f"{instId} 当前非空头趋势，跳过空单挂单")

    except Exception as e:
        error_message = f'Error processing {instId}: {e}'
        logger.error(error_message)
        send_feishu_notification(error_message)

def main():
    fetch_and_store_all_instruments()
    inst_ids = list(trading_pairs_config.keys())  # 获取所有币对的ID
    batch_size = 5  # 每批处理的数量

    while True:
        for i in range(0, len(inst_ids), batch_size):
            batch = inst_ids[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = [executor.submit(process_pair, instId, trading_pairs_config[instId]) for instId in batch]
                for future in as_completed(futures):
                    future.result()  # Raise any exceptions caught during execution

        time.sleep(monitor_interval)

if __name__ == '__main__':
    main()
