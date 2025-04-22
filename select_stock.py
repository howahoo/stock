# -*-coding=utf-8-*-
# 适用 tushare 0.7.5
__author__ = 'Rocky'
'''
http://30daydo.com
Contact: weigesysu@qq.com
'''
import tushare as ts
import pandas as pd
import os, datetime, time
import numpy as np
try:
    # Python 2
    import Queue
except ImportError:
    # Python 3
    import queue as Queue
from toolkit import Toolkit
from threading import Thread

q = Queue.Queue()

# 用来选股用的
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

from configure.settings import DBSelector, config
db_selector = DBSelector()
engine = db_selector.get_engine('db_stock', type_='local')

# 设置tushare pro的token
ts.set_token(config.get('ts_token'))
pro = ts.pro_api()

# 缺陷： 暂时不能保存为excel
class filter_stock():
    def __init__(self,retry=5,local=False):
        if local:
            for i in range(retry):
                try:
                    # 使用pro接口获取股票基本信息
                    self.bases_save = pro.stock_basic(exchange='', list_status='L', 
                                                    fields='ts_code,symbol,name,area,industry,list_date')
                    # 转换代码格式
                    self.bases_save['code'] = self.bases_save['symbol']
                    self.bases_save.to_csv('bases.csv')
                    self.bases_save.to_sql('bases',engine,if_exists='replace')
                    if not self.bases_save.empty:
                        break
                except Exception as e:
                    print(f"获取数据失败: {str(e)}")
                    if i>=4:
                        self.bases_save=pd.DataFrame()
                        exit()
                    continue
        else:
            self.bases_save = pd.read_sql('bases',engine,index_col='index')
            self.base = self.bases_save

        self.today = time.strftime("%Y-%m-%d", time.localtime())
        self.all_code = self.bases_save['code'].values
        self.working_count = 0
        self.mystocklist = Toolkit.read_stock('mystock.csv')

    def get_stock_basics(self):
        """获取所有股票的基本面数据"""
        try:
            # 获取基本面数据
            df = pro.daily_basic(trade_date=self.today.replace('-', ''),
                               fields='ts_code,turnover_rate,volume_ratio,pe,pb')
            return df
        except Exception as e:
            print(f"获取基本面数据失败: {str(e)}")
            return pd.DataFrame()

    def get_area(self, area, writeable=False):
        """获取特定地区的股票"""
        user_area = self.bases_save[self.bases_save['area'] == area]
        if writeable:
            filename = area + '.csv'
            user_area.to_csv(filename)
        return user_area

    def fetch_new_ipo(self, start_date, writeable=False):
        """获取新股信息"""
        try:
            # 使用pro接口获取IPO股票信息
            df = pro.new_share(start_date=start_date)
            if writeable:
                df.to_csv("New_IPO.csv")
            return df
        except Exception as e:
            print(f"获取新股数据失败: {str(e)}")
            return pd.DataFrame()

    def get_daily_data(self, code, start_date=None, end_date=None):
        """获取日线数据"""
        try:
            # 转换代码格式
            if len(code) == 6:
                if code.startswith('6'):
                    ts_code = code + '.SH'
                else:
                    ts_code = code + '.SZ'
            else:
                ts_code = code
            
            if start_date is None:
                start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y%m%d')
            if end_date is None:
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            return df
        except Exception as e:
            print(f"获取日线数据失败: {str(e)}")
            return pd.DataFrame()

    def select_by_basics(self, pe_range=(0, 50), pb_range=(0, 5), 
                        turnover_min=1.0, volume_ratio_min=1.0):
        """根据基本面数据筛选股票"""
        try:
            # 获取基本面数据
            df = self.get_stock_basics()
            if df.empty:
                return []
            
            # 条件筛选
            condition = (
                (df['pe'] >= pe_range[0]) & (df['pe'] <= pe_range[1]) &  # PE范围
                (df['pb'] >= pb_range[0]) & (df['pb'] <= pb_range[1]) &  # PB范围
                (df['turnover_rate'] >= turnover_min) &  # 换手率
                (df['volume_ratio'] >= volume_ratio_min)  # 量比
            )
            
            selected = df[condition]
            
            # 获取股票名称并组织结果
            result = []
            for _, row in selected.iterrows():
                code = row['ts_code'][:6]
                try:
                    name = self.bases_save[self.bases_save['code'] == code]['name'].values[0]
                    result.append([code, name, row['pe'], row['pb'], 
                                 row['turnover_rate'], row['volume_ratio']])
                except:
                    continue
            
            return result
            
        except Exception as e:
            print(f"基本面选股失败: {str(e)}")
            return []

    def macd(self, days=30):
        """获取MACD指标"""
        result = []
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')
        end_date = datetime.datetime.now().strftime('%Y%m%d')
        
        for code in self.all_code:
            print(f"处理股票: {code}")
            try:
                df = self.get_daily_data(code, start_date, end_date)
                if df.empty:
                    continue
                    
                # 计算MA5和MA10
                df['ma5'] = df['close'].rolling(window=5).mean()
                df['ma10'] = df['close'].rolling(window=10).mean()
                
                # 计算MACD
                exp12 = df['close'].ewm(span=12, adjust=False).mean()
                exp26 = df['close'].ewm(span=26, adjust=False).mean()
                df['macd'] = exp12 - exp26
                df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
                df['hist'] = df['macd'] - df['signal']
                
                # 获取最新的值
                latest = df.iloc[0]
                
                # 同时满足：
                # 1. 5日均线上穿10日均线
                # 2. MACD柱状图由负转正
                if (latest['ma5'] > latest['ma10'] and 
                    latest['hist'] > 0 and df.iloc[1]['hist'] < 0):
                    stock_name = self.bases_save[self.bases_save['code'] == code]['name'].values[0]
                    result.append([code, stock_name])
                    print(f"选中: {code} {stock_name}")
            except Exception as e:
                print(f"处理股票{code}时出错: {str(e)}")
                continue
                
        return result

    # 保存为excel 文件 这个时候csv 乱码,excel正常.
    def save_data_excel(self):
        df = ts.get_stock_basics()

        df.to_csv(self.today + '.csv', encoding='gbk')
        df_x = pd.read_csv(self.today + '.csv', encoding='gbk')
        df_x.to_excel(self.today + '.xls', encoding='gbk')
        os.remove(self.today + '.csv')

    def insert_garbe(self):
        print('*' * 30)
        print('\n')

    def showInfo(self, df):
        print('*' * 30)
        print('\n')
        print(df.info())
        print('*' * 30)
        print('\n')
        print(df.dtypes)
        self.insert_garbe()
        print(df.describe())

    # 计算每个地区有多少上市公司
    def count_area(self, writeable=False):
        count = self.base['area'].value_counts()
        print(count)
        print(type(count))
        if writeable:
            count.to_csv('各省的上市公司数目.csv')
        return count

    # 获取所有地区的分类个股
    def get_all_location(self):
        series = self.count_area()
        index = series.index
        for i in index:
            name = unicode(i)
            self.get_area(name, writeable=True)

    # 找出指定日期后的次新股
    def fetch_new_ipo(self, start_time, writeable=False):
        # 需要继续转化为日期类型

        df = self.base.loc[self.base['timeToMarket'] > start_time]
        df.sort_values('timeToMarket', inplace=True, ascending=False)
        if writeable == True:
            df.to_csv("New_IPO.csv")
        # sum_a=df['pe'].sum()

        pe_av = df[df['pe'] != 0]['pe'].mean()
        pe_all_av = self.base[self.base['pe'] != 0]['pe'].mean()
        print(u"平均市盈率为 ", pe_av)
        print('A股的平均市盈率为 ', pe_all_av)
        return df

    # 获取成分股
    def get_chengfenggu(self, writeable=False):
        s50 = ts.get_sz50s()
        if writeable == True:
            s50.to_excel('sz50.xls')
        list_s50 = s50['code'].values.tolist()
        # print(type(s50))
        # print(type(list_s50))
        # 返回list类型
        return list_s50

    # 计算一个票从最高位到目前 下跌多少 计算跌幅
    def drop_down_from_high(self, start, code):

        end_day = datetime.date(datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
        end_day = end_day.strftime("%Y-%m-%d")
        # print(e)nd_day
        # print(start)
        total = ts.get_k_data(code=code, start=start, end=end_day)
        # print(total)
        high = total['high'].max()
        high_day = total.loc[total['high'] == high]['date'].values[0]

        print(high)
        print(high_day)
        current = total['close'].values[-1]
        print(current)
        percent = round((current - high) / high * 100, 2)
        print(percent)
        return percent

    def loop_each_cixin(self):
        df = self.fetch_new_ipo(20170101, writeable=False)
        all_code = df['code'].values
        print(all_code)
        # exit()
        percents = []
        for each in all_code:
            print(each)
            # print(type(each))
            percent = self.drop_down_from_high('2017-01-01', each)
            percents.append(percent)

        df['Drop_Down'] = percents

        # print(df)

        df.sort_values('Drop_Down', ascending=True, inplace=True)
        # print(df)
        df.to_csv(self.today + '_drop_Down_cixin.csv')

    # 获取所有的ma5>ma10
    def macd(self):
        # df=self.fetch_new_ipo(writeable=True)
        # all_code=df['code'].values
        # all_code=self.get_all_code()
        # print(all_code)
        result = []
        for each_code in self.all_code:
            print(each_code)
            try:
                df_x = ts.get_k_data(code=each_code, start='2017-03-01')
            # 只找最近一个月的，所以no item的是停牌。
            except:
                print("Can't get k_data")
                continue
            if len(df_x) < 11:
                # return
                print("no item")
                continue
            ma5 = df_x['close'][-5:].mean()
            ma10 = df_x['close'][-10:].mean()
            if ma5 > ma10:
                # print("m5>m10: ",each_code," ",self.base[self.base['code']==each_code]['name'].values[0], "ma5: ",ma5,' m10: ',ma10)
                temp = [each_code, self.base[self.base['code'] == each_code]['name'].values[0]]
                print(temp)
                result.append(temp)
        print(result)
        print("Done")
        return result

    # 返回所有股票的代码
    def get_all_code(self):
        return self.all_code

    # 获取成交量的ma5 或者10
    def volume_calculate(self, codes):
        delta_day = 180 * 7 / 5
        end_day = datetime.date(datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
        start_day = end_day - datetime.timedelta(delta_day)

        start_day = start_day.strftime("%Y-%m-%d")
        end_day = end_day.strftime("%Y-%m-%d")
        print(start_day)
        print(end_day)
        result_m5_large = []
        result_m5_small = []
        for each_code in codes:
            # print(e)ach_code
            try:
                df = ts.get_k_data(each_code, start=start_day, end=end_day)
                print(df)
            except Exception as e:
                print("Failed to get")
                print(e)
                continue

            if len(df) < 20:
                # print("not long enough")
                continue
            print(each_code)
            all_mean = df['volume'].mean()
            m5_volume_m = df['volume'][-5:].mean()
            m10_volume_m = df['volume'][-10:].mean()
            last_vol = df['volume'][-1]  # 这里会不会有问题？？？
            # 在这里分几个分支，放量 180天均量的4倍
            if m5_volume_m > (4.0 * all_mean):
                print("m5 > m_all_avg ")
                print(each_code,)
                temp = self.base[self.base['code'] == each_code]['name'].values[0]
                print(temp)
                result_m5_large.append(each_code)

            # 成交量萎缩
            if last_vol < (m5_volume_m / 3.0):
                result_m5_small.append(each_code)
        return result_m5_large, result_m5_large

    def turnover_check(self):
        delta_day = 60 * 7 / 5
        end_day = datetime.date(datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
        start_day = end_day - datetime.timedelta(delta_day)

        start_day = start_day.strftime("%Y-%m-%d")
        end_day = end_day.strftime("%Y-%m-%d")
        print(start_day)
        print(end_day)
        for each_code in self.all_code:
            try:
                df = ts.get_hist_data(code=each_code, start=start_day, end=end_day)
            except:
                print("Failed to get data")
                continue
            mv5 = df['v_ma5'][-1]
            mv20 = df['v_ma20'][-1]
            mv_all = df['volume'].mean()


    # 写入csv文件
    def write_to_text(self):
        print("On write")
        r = self.macd()
        filename = self.today + "-macd.csv"
        f = open(filename, 'w')
        for i in r:
            f.write(i[0])
            f.write(',')
            f.write(i[1])
            f.write('\n')
        f.close()

    def saveList(self, l, name):
        f = open(self.today + name + '.csv', 'w')
        if len(l) == 0:
            return False
        for i in l:
            f.write(i)
            f.write(',')
            name = self.base[self.base['code'] == i]['name'].values[0]
            f.write(name)
            f.write('\n')
        f.close()
        return True

    # 读取自己的csv文件
    def read_csv(self):
        filename = self.today + "-macd.csv"
        df = pd.read_csv(filename)
        print(df)

    # 持股从高点下跌幅度
    def own_drop_down(self):
        for i in self.mystocklist:
            print(i)
            self.drop_down_from_high(code=i, start='2017-01-01')
            print('\n')

    # 持股跌破均线
    def _break_line(self, codes, k_type):
        delta_day = 60 * 7 / 5
        end_day = datetime.date(datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
        start_day = end_day - datetime.timedelta(delta_day)

        start_day = start_day.strftime("%Y-%m-%d")
        end_day = end_day.strftime("%Y-%m-%d")
        print(start_day)
        print(end_day)
        all_break = []

        for i in codes:
            try:
                df = ts.get_hist_data(code=i, start=start_day, end=end_day)
                if len(df) == 0:
                    continue
            except Exception as e:
                print(e)
                continue
            else:
                self.working_count = self.working_count + 1
                current = df['close'][0]
                ma5 = df['ma5'][0]
                ma10 = df['ma10'][0]
                ma20 = df['ma20'][0]
                ma_dict = {'5': ma5, '10': ma10, '20': ma20}
                ma_x = ma_dict[k_type]
                # print(ma_x)
                if current < ma_x:
                    print('破位')
                    print(i, " current: ", current)
                    print(self.base[self.base['code'] == i]['name'].values[0], " ")
                    print("holding place: ", ma_x)
                    print("Break MA", k_type, "\n")
                    all_break.append(i)
        return all_break

    # 检查自己的持仓或者市场所有破位的
    def break_line(self, code, k_type='20', writeable=False, mystock=False):

        all_break = self._break_line(code, k_type)
        l = len(all_break)
        beaking_rate = l * 1.00 / self.working_count * 100
        print("how many break: ", l)
        print("break Line rate ", beaking_rate)
        if mystock == False:
            name = '_all_'
        else:
            name = '_my__'
        if writeable:
            f = open(self.today + name + 'break_line_' + k_type + '.csv', 'w')
            f.write("Breaking rate: %f\n\n" % beaking_rate)
            f.write('\n'.join(all_break))
            f.close()

    def _break_line_thread(self, codes, k_type='5'):
        delta_day = 60 * 7 / 5
        end_day = datetime.date(datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
        start_day = end_day - datetime.timedelta(delta_day)

        start_day = start_day.strftime("%Y-%m-%d")
        end_day = end_day.strftime("%Y-%m-%d")
        print(start_day)
        print(end_day)
        all_break = []
        for i in codes:
            try:
                df = ts.get_hist_data(code=i, start=start_day, end=end_day)
                if len(df) == 0:
                    continue
            except Exception as e:
                print(e)
                continue
            else:
                self.working_count = self.working_count + 1
                current = df['close'][0]
                ma5 = df['ma5'][0]
                ma10 = df['ma10'][0]
                ma20 = df['ma20'][0]
                ma_dict = {'5': ma5, '10': ma10, '20': ma20}
                ma_x = ma_dict[k_type]
                # print(ma_x)
                if current > ma_x:
                    print(i, " current: ", current)
                    print(self.base[self.base['code'] == i]['name'].values[0], " ")

                    print("Break MA", k_type, "\n")
                    all_break.append(i)
        q.put(all_break)

    def multi_thread_break_line(self, ktype='20'):
        total = len(self.all_code)
        thread_num = 10
        delta = total / thread_num
        delta_left = total % thread_num
        t = []
        i = 0
        for i in range(thread_num):
            sub_code = self.all_code[i * delta:(i + 1) * delta]
            t_temp = Thread(target=self._break_line_thread, args=(sub_code, ktype))
            t.append(t_temp)
        if delta_left != 0:
            sub_code = self.all_code[i * delta:i * delta + delta_left]
            t_temp = Thread(target=self._break_line_thread, args=(sub_code, ktype))
            t.append(t_temp)

        for i in range(len(t)):
            t[i].start()

        for j in range(len(t)):
            t[j].join()
        result = []
        print("working done")
        while not q.empty():
            result.append(q.get())
        ff = open(self.today + '_high_m%s.csv' % ktype, 'w')
        for kk in result:
            print(kk)
            for k in kk:
                ff.write(k)
                ff.write(',')
                ff.write(self.base[self.base['code'] == k]['name'].values[0])
                ff.write('\n')

        ff.close()

        # 计算大盘的相关系，看关系如何

    def relation(self):
        sh_index = ts.get_k_data('000001', index=True, start='2012-01-01')
        sh = sh_index['close'].values
        print(sh)
        vol_close = sh_index.corr()
        print(vol_close)
        '''
        sz_index=ts.get_k_data('399001',index=True)
        sz=sz_index['close'].values
        print(sz)

        cy_index=ts.get_k_data('399006',index=True)
        s1=Series(sh)
        s2=Series(sz)
        print(s1.corr(s2))
        '''

    # 寻找业绩两年未负的，以防要st
    def profit(self):
        df_2016 = ts.get_report_data(2016, 4)

        # 第四季度就是年报
        # df= df.sort_values('profits_yoy',ascending=False)
        # df.to_excel('profit.xls')
        df_2015 = ts.get_report_data(2015, 4)
        df_2016.to_excel('2016_report.xls')
        df_2015.to_excel('2015_report.xls')
        code_2015_lost = df_2015[df_2015['net_profits'] < 0]['code'].values
        code_2016_lost = df_2016[df_2016['net_profits'] < 0]['code'].values

        print(code_2015_lost)
        print(code_2016_lost)
        two_year_lost = []
        # two_year_lost_name=[]
        for i in code_2015_lost:
            if i in code_2016_lost:
                print(i,)
                # name=self.base[self.base['code']==i].values[0]
                two_year_lost.append(i)

        self.saveList(two_year_lost, 'st_dangours.csv')

        # df_2014=ts.get_report_data(2014,4)

    def mydaily_check(self):
        self.break_line(self.mystocklist, k_type='5', writeable=True, mystock=True)

    def all_stock(self):
        self.multi_thread_break_line('20')

#破净资产的股票
def get_break_bvps():
    base_info = ts.get_stock_basics()
    current_prices = ts.get_today_all()


    current_prices[current_prices['code'] == '000625']['trade'].values[0]
    base_info.loc['000625']['bvps']

def main():
    # 创建数据目录
    folder = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(folder):
        os.mkdir(folder)
    os.chdir(folder)

    # 创建选股器实例
    stock_filter = filter_stock(local=True)
    
    print("\n=== 开始选股 ===")
    
    # 1. 基本面选股
    print("\n1. 基于基本面数据选股...")
    basic_stocks = stock_filter.select_by_basics(
        pe_range=(0, 30),  # PE范围0-30
        pb_range=(0, 3),   # PB范围0-3
        turnover_min=3.0,  # 换手率>3%
        volume_ratio_min=1.5  # 量比>1.5
    )
    print(f"基本面选股结果数量: {len(basic_stocks)}")
    if basic_stocks:
        df_basic = pd.DataFrame(basic_stocks, 
                              columns=['代码', '名称', 'PE', 'PB', '换手率', '量比'])
        df_basic.to_csv('basic_selected_stocks.csv', index=False)
        print("基本面选股结果已保存到 basic_selected_stocks.csv")
    
    # 2. 技术面选股
    print("\n2. 基于MACD策略选股...")
    macd_stocks = stock_filter.macd()
    print(f"MACD策略选出的股票数量: {len(macd_stocks)}")
    if macd_stocks:
        pd.DataFrame(macd_stocks, columns=['代码', '名称']).to_csv('macd_selected_stocks.csv', index=False)
        print("MACD选股结果已保存到 macd_selected_stocks.csv")
    
    # 3. 获取上海地区的股票（可选）
    print("\n3. 获取上海地区股票...")
    sh_stocks = stock_filter.get_area('上海', writeable=True)
    print(f"上海地区股票数量: {len(sh_stocks)}")
    
    # 4. 获取新股信息（可选）
    print("\n4. 获取近期新股...")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y%m%d')
    new_stocks = stock_filter.fetch_new_ipo(start_date, writeable=True)
    print(f"近30天新股数量: {len(new_stocks)}")
    
    print("\n=== 选股完成 ===")

if __name__ == "__main__":
    start_time = datetime.datetime.now()
    print(start_time)
    main()
    end_time = datetime.datetime.now()
    print(end_time)
    print("time use : ", (end_time - start_time).seconds)
