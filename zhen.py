import time
import okx.Trade_api as TradeAPI
import okx.Public_api as PublicAPI
import okx.Market_api as MarketAPI
import json
import logging
from logging.handlers import TimedRotatingFileHandler

with open('config.json', 'r') as f:
    config = json.load(f)
# 提取OKX部分的配置
okx_config = config['okx']

# 配置 OKX 第三方库
trade_api = TradeAPI.TradeAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
market_api = MarketAPI.MarketAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
public_api = PublicAPI.PublicAPI(okx_config["apiKey"], okx_config["secret"], okx_config["password"], False, '0')
# 配置日志
log_file = "log/okx.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 使用 TimedRotatingFileHandler 以天为单位进行日志分割
file_handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
file_handler.suffix = "%Y-%m-%d"  # 设置日志文件名的后缀格式，例如 multi_asset_bot.log.2024-11-05
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger = logger

# 获取标记价格
def get_mark_price(instId):
    # 这里需要调用一个获取标记价格的API接口
    response = market_api.get_ticker(instId)

    if 'data' in response and len(response['data']) > 0:
        # 第一条数据中的 'last' 字段
        last_price = response['data'][0]['last']
        return float(last_price)
    else:
        raise ValueError("Unexpected response structure or missing 'last' key")


def cancel_all_orders(instId):
    # 获取当前挂单列表
    open_orders = trade_api.get_order_list(instId=instId, state='live')
    order_ids = [order['ordId'] for order in open_orders['data']]

    # 取消所有挂单
    for ord_id in order_ids:
        trade_api.cancel_order(instId=instId, ordId=ord_id)
    print("挂单取消成功.")


def place_order(instId, price):
    amount_usdt = 20  # 下单金额，1x杠杆算
    response = public_api.convert_contract_coin(type='1', instId=instId, sz=str(amount_usdt), px=str(price),
                                                unit='usdt', opType='open')

    if response['code'] == '0':
        sz = response['data'][0]['sz']

        if float(sz) > 0:
            # 下一个限价买单
            order_result = trade_api.place_order(
                instId=instId,
                tdMode='cash',  # 请根据实际情况设置交易模式
                side='buy',
                ordType='limit',
                sz=sz,  # 使用转换后的张数
                px=str(price)  # 价格需为字符串格式
            )
            print(f"下单成功: {order_result}")
        else:
            print("计算出的合约张数太小，无法下单。")
    else:
        print(f"转换失败: {response['msg']}")


def main():
    instId = 'CTC-USDT-SWAP'  # 设置交易对
    while True:
        try:
            mark_price = get_mark_price(instId)
            target_price = mark_price * 0.99

            cancel_all_orders(instId)
            place_order(instId, target_price)

            time.sleep(60)  # 每60秒运行一次
        except Exception as e:
            print(f'An error occurred: {e}')
            time.sleep(60)  # 若发生错误，等待60秒后重试


if __name__ == '__main__':
    main()
