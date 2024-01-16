import sqlalchemy
import json
import base64
import configparser

config = configparser.ConfigParser()
config.read('config.ini')
cfg = config['main']

connection_name = str(cfg['connection_name']) 
table_name_main = str(cfg['table_name_main'])
table_name_lamp = str(cfg['table_name_lamp'])
db_name = str(cfg['db_name'])
db_user = str(cfg['db_user'])
db_password = str(cfg['db_password'])

driver_name = 'mysql+pymysql'
query_string = dict({"unix_socket": "/cloudsql/{}".format(connection_name)})

def insert(event,context):
    if 'data' in event:
        jsonStr = base64.b64decode(event['data']).decode('utf-8')
        jsonDict = json.loads(jsonStr)
        stat = 'MAIN: ' + insert_main(jsonDict) + '\n'
        stat = stat + 'LAMP: ' + update_light(jsonDict) 
        return stat

def insert_main(jsonDict):
    fieldNames = ''
    fieldValues = ''

    musthave = ['date','time','devID','gwyID']
    if not all(key in jsonDict for key in musthave):
        return 'Insufficient information'
    
    i = 0
    if 'temp' in jsonDict:
        fieldNames = fieldNames + ',Temperature'
        fieldValues = fieldValues + ',' + str(jsonDict['temp'])
        i += 1
    if 'rh' in jsonDict:
        fieldNames = fieldNames + ',RH'
        fieldValues = fieldValues + ',' + str(jsonDict['rh'])
        i += 1
    if 'lux' in jsonDict:
        fieldNames = fieldNames + ',Illuminance'
        fieldValues = fieldValues + ',' + str(jsonDict['lux'])
        i += 1
    if 'co2' in jsonDict:
        fieldNames = fieldNames + ',CO2'
        fieldValues = fieldValues + ',' + str(jsonDict['co2'])
        i += 1
    if 'spl' in jsonDict:
        fieldNames = fieldNames + ',SPL'
        fieldValues = fieldValues + ',' + str(jsonDict['spl'])
        i += 1
    
    if i == 0:
        return 'No IEQ data included'

    fieldNames = fieldNames + ',Datetime'
    fieldValues = fieldValues + ',\'' + str(jsonDict['date']) + ' ' + str(jsonDict['time']) + '\''

    fieldNames = fieldNames + ',DeviceID'
    fieldValues = fieldValues + ',\'' + str(jsonDict['devID']) + '\''
    fieldNames = fieldNames + ',GatewayID'
    fieldValues = fieldValues + ',\'' + str(jsonDict['gwyID']) + '\''

    fieldNames = fieldNames[1:] ; fieldValues = fieldValues[1:]

    insert_query = f'INSERT INTO {table_name_main} ({fieldNames}) VALUES ({fieldValues});'
    return sql_query(insert_query)

def update_light(jsonDict):
    if 'lamp' in jsonDict and 'devID' in jsonDict:
        update_query = f'''
        UPDATE {table_name_lamp}
        SET Lamp = {int(jsonDict['lamp'])}, Datetime = SYSDATE()
        WHERE DeviceID = '{str(jsonDict['devID'])}'
        '''
        return sql_query(update_query)
    
    else:
        return 'No lamp information'

def sql_query(query):
    stmt = sqlalchemy.text(query)
    
    db = sqlalchemy.create_engine(
    sqlalchemy.engine.url.URL(
        drivername=driver_name,
        username=db_user,
        password=db_password,
        database=db_name,
        query=query_string,
    ),
    pool_size=5,
    max_overflow=2,
    pool_timeout=30,
    pool_recycle=1800
    )
    try:
        with db.connect() as conn:
            conn.execute(stmt)
    except Exception as e:
        return 'Error: {}'.format(str(e))
    return 'query ok'
