# jiezhen
读秒循环接针高频

config_bak.json  改成config.json

#### 视频说明地址：https://www.youtube.com/watch?v=b-LhdQomOxk
 
#### apiKey: OKX API 的公钥，用于身份验证。
#### secret: OKX API 的私钥，用于签名请求。
#### password: OKX 的交易密码（或 API 密码）。
#### leverage: 默认持仓杠杆倍数
#### feishu_webhook: 飞书通知地址
#### monitor_interval: 循环间隔周期 / 单位秒


## 每个交易对都可以单独设置其交易参数：
#### long_amount_usdt: 做多交易时每笔订单分配的资金量（以 USDT 为单位）。
#### short_amount_usdt: 做空交易时每笔订单分配的资金量（以 USDT 为单位）。
#### value_multiplier: 用于放大交易价值的乘数，适合调整风险/回报比。