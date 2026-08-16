import loadStocks as ld
import stockPolicy as sp

db=ld.connectDB()
df=ld.getStockBasic()
ld.createStockTable(df)
ld.loadAllBasic(df)
#将DF数据帧中从开始日期到结束日期之间的交易记录导入每支股票的数据库
ld.insertNewTransactonRecordForAllStocks(df,start_date='20260130',end_date='20260317')

# 放量涨幅筛选：当日成交量>=前日3倍 且 涨幅>6%
# 结果写入sm数据库的st_daily_signal表
# sp.getLiangJiaFangLiang(startDate='20260101', endDate='20260815')
