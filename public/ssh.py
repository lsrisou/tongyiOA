import pymysql as mysql
from sshtunnel import SSHTunnelForwarder

# SSH连接参数(解决内网数据库连接)
ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'

# 数据库连接参数(办公系统)
db_host = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
db_port = 3306
db_username = 'deshengoa'
db_password = 'EZayyR4qDu7vA3EwSdeKAE8n'
db_name = 'deshengoa'

# 数据库连接参数(统一AI用户)
db_host_ty = 'rm-2zeud24li0c5tkt2r.mysql.rds.aliyuncs.com'
db_port_ty = 3306
db_username_ty = 'tyuser'
db_password_ty = 'NzrxD4P3p0gkPJz3KWhZ4I'
db_name_ty = 'tongyiedu'

# 数据库连接参数(统一AI资源)
db_host_ty = 'rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com'
db_port_ty = 3306
db_username_ty = 'tyedu'
db_password_ty = 'YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1'
db_name_ty = 'tongyiedu_analysis'

server = SSHTunnelForwarder((ssh_host, ssh_port), ssh_username=ssh_username, ssh_password=ssh_password, remote_bind_address=(db_host, db_port))
server.start()
conn = mysql.connect(host='127.0.0.1', port=server.local_bind_port, user=db_username, passwd=db_password, db=db_name)

server_ty = SSHTunnelForwarder((ssh_host, ssh_port), ssh_username=ssh_username, ssh_password=ssh_password, remote_bind_address=(db_host_ty, db_port_ty))
server_ty.start()
conn_ty = mysql.connect(host='127.0.0.1', port=server_ty.local_bind_port, user=db_username_ty, passwd=db_password_ty, db=db_name_ty)