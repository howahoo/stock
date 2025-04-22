# -*-coding=utf-8-*-
#常用的工具集合
__author__ = 'Rocky'
'''
http://30daydo.com
Contact: weigesysu@qq.com
'''
import codecs
import os
import pandas as pd

class Toolkit():
    @staticmethod
    def save2file( filename, content):
        # 保存为文件
        filename = filename + ".txt"
        f = open(filename, 'a')
        f.write(content)
        f.close()

    @staticmethod
    def save2filecn( filename, content):
        # 保存为文件
        #filename = filename + ".txt"
        f = codecs.open(filename, 'a',encoding='utf-8')
        f.write(content)
        f.close()

    @staticmethod
    def getUserData(cfg_file):
        f=open(cfg_file,'r')
        account={}
        for i in f.readlines():
            ctype,passwd=i.split('=')
            #print(ctype)
            #print(passwd)
            account[ctype.strip()]=passwd.strip()

        return account

    @staticmethod
    def read_stock(filename):
        try:
            df = pd.read_csv(filename)
            return df
        except Exception as e:
            print(f"读取文件失败: {str(e)}")
            return None

    @staticmethod
    def save_stock(filename, data):
        try:
            if isinstance(data, pd.DataFrame):
                data.to_csv(filename, index=False)
            else:
                df = pd.DataFrame(data)
                df.to_csv(filename, index=False)
            return True
        except Exception as e:
            print(f"保存文件失败: {str(e)}")
            return False