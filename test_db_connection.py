import pymysql
from configure.settings import DBSelector

def test_connection():
    try:
        # 创建数据库选择器
        db_selector = DBSelector()
        
        # 获取数据库连接
        conn = db_selector.get_mysql_conn(db='_Main', type_='local')
        
        if conn is None:
            print("无法连接到数据库")
            return
            
        # 创建游标对象
        cursor = conn.cursor()
        
        # 执行简单的SQL查询
        cursor.execute("SELECT VERSION()")
        
        # 获取结果
        version = cursor.fetchone()
        print(f"数据库连接成功！MySQL版本: {version[0]}")
        
        # 关闭游标和连接
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"连接失败：{str(e)}")

if __name__ == "__main__":
    test_connection() 