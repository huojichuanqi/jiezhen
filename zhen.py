import time
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import json
import logging
import requests
from logging.handlers import TimedRotatingFileHandler

# 读取配置文件
with open('config.json', 'r') as f:
    config = json.load(f)

# 提取配置
okx_config = config['okx']
trading_pairs_config = config.get('tradingPairs', {})
monitor_interval = config.get('monitor_interval', 60)  # 默认60秒
feishu_webhook = config.get('feishu_webhook', '')

trade_api = TradeAPI.TradeAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
market_api = MarketAPI.MarketAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
public_api = PublicAPI.PublicAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')

log_file = "log/okx.log"
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


def send_feishu_notification(message):
    if feishu_webhook:
        headers = {'Content-Type': 'application/json'}
        data = {"msg_type": "text", "content": {"text": message}}
        response = requests.post(feishu_webhook, headers=headers, json=data)
        if response.status_code == 200:
            print("飞书通知发送成功")
        else:
            print(f"飞书通知发送失败: {response.text}")
    else:
        print("飞书Webhook URL未配置")


def get_mark_price(instId):
    response = market_api.get_ticker(instId)
    if 'data' in response and len(response['data']) > 0:
        last_price = response['data'][0]['last']
        return float(last_price)
    else:
        raise ValueError("Unexpected response structure or missing 'last' key")


def get_historical_klines(instId, bar='1m', limit=30):
    response = market_api.get_candlesticks(instId, bar=bar, limit=limit)
    if 'data' in response and len(response['data']) > 0:
        # Return the Kline data which includes [timestamp, open, high, low, close, volume]
        return response['data']
    else:
        raise ValueError("Unexpected response structure or missing candlestick data")


def calculate_atr(klines, period=14):
    trs = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return atr


def calculate_average_amplitude(klines, period=14):
    amplitudes = []
    for i in range(len(klines) - period, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        close = float(klines[i][4])  # 使用收盘价作为基准
        amplitude = ((high - low) / close) * 100  # 计算高低价差的百分比
        amplitudes.append(amplitude)
    average_amplitude = sum(amplitudes) / len(amplitudes)
    return average_amplitude



def cancel_all_orders(instId):
    open_orders = trade_api.get_order_list(instId=instId, state='live')
    order_ids = [order['ordId'] for order in open_orders['data']]
    for ord_id in order_ids:
        trade_api.cancel_order(instId=instId, ordId=ord_id)
    logger.info(f"{instId}挂单取消成功.")


def place_order(instId, price, amount_usdt):
    response = public_api.convert_contract_coin(type='1', instId=instId, sz=str(amount_usdt), px=str(price),
                                                unit='usdt', opType='open')
    if response['code'] == '0':
        sz = response['data'][0]['sz']
        if float(sz) > 0:
            order_result = trade_api.place_order(
                instId=instId,
                tdMode='isolated',
                side='buy',
                ordType='limit',
                sz=sz,
                px=str(price)
            )
            print(f"{instId}下单结果: {order_result}")

            # send_feishu_notification(f"{instId}下单结果: {order_result}")
        else:
            logger.info(f"{instId}计算出的合约张数太小，无法下单。")
            # send_feishu_notification(f"{instId}计算出的合约张数太小，无法下单。")
    else:
        logger.info(f"{instId}转换失败: {response['msg']}")
        send_feishu_notification(f"{instId}转换失败: {response['msg']}")


def main():
    while True:
        try:
            for instId, pair_config in trading_pairs_config.items():
                mark_price = get_mark_price(instId)
                klines = get_historical_klines(instId)
                atr = calculate_atr(klines)
                # print(klines)

                # 打印ATR和当前价格/ATR比值
                price_atr_ratio = (mark_price / atr) / 100
                # print(atr)
                # print(price_atr_ratio)
                # continue
                logger.info(f"{instId} ATR: {atr}, 当前价格/ATR比值: {price_atr_ratio:.3f}")

                average_amplitude = calculate_average_amplitude(klines)

                logger.info(f"{instId} ATR: {atr}, 平均振幅: {average_amplitude:.2f}%")

                # 选择较小的值，并确保最终值不小于0.005
                selected_value = min(average_amplitude, price_atr_ratio)

                selected_value = max(selected_value, 0.5)

                # price_factor = pair_config.get('price_factor', 0.99)  # 默认值0.99
                # price_factor = 1 - price_atr_ratio  # 接针价差
                price_factor = 1 - selected_value / 100  # 确保price_factor不为负


                amount_usdt = pair_config.get('amount_usdt', 20)  # 默认值20
                target_price = mark_price * price_factor
                logger.info(f"{instId} ATR: {atr}, 当前挂单价差: {price_factor:.3f}，价格: {target_price:.6f}")



                cancel_all_orders(instId)
                place_order(instId, target_price, amount_usdt)

            time.sleep(monitor_interval)
        except Exception as e:
            error_message = f'An error occurred: {e}'
            logger.error(error_message)
            send_feishu_notification(error_message)
            time.sleep(monitor_interval)

if __name__ == '__main__':
    main()
