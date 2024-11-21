# jiezhen
读秒循环接针

环境：python3.9, 

开平仓模式 ，不支持单向持仓


策略原理：上次在火币看到一些很长的针，就想着如何把针接住，本质很简单，用ema判断短期趋势，尽可能下面挂单接住插下来的针

如果跑15m周期以上，建议用1h的ema判断多空，或者人工介入判断


config_bak.json  改成config.json

zhen.py 跟 zhen_2.py的区别是：https://x.com/huojichuanqi/status/1858991226877603902

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

打赏地址trc20: TUunBuqQ1ZDYt9WrA3ZarndFPQgefXqZAM
