
--Create new table main data
USE tugas_scada_tim7_db1;
CREATE TABLE ieq_table_demo (
    Number INT NOT NULL AUTO_INCREMENT,
    Temperature FLOAT,
    RH FLOAT,
    Illuminance FLOAT,
    CO2 FLOAT,
    SPL FLOAT,
    Datetime DATETIME,
    DeviceID VARCHAR(255), 
    GatewayID VARCHAR(255),
    PRIMARY KEY(Number)
);

--Create new table lamp data
USE tugas_scada_tim7_db1;
CREATE TABLE ieq_table_lamp(
    Number INT NOT NULL AUTO_INCREMENT,
    DeviceID VARCHAR(255),
    Lamp BOOLEAN,
    Datetime DATETIME,
    PRIMARY KEY(Number)
);

--Insert lamp data
USE tugas_scada_tim7_db1;
INSERT INTO ieq_table_lamp (DeviceID, Lamp, Datetime)
VALUES ('DEV003',0,SYSDATE());

--Update lamp data
USE tugas_scada_tim7_db1;
UPDATE ieq_table_lamp
SET Lamp = 1
WHERE DeviceID = 'DEV003';

--Extract all data in database
USE ieq_data;
SELECT * FROM ieq_table;

--Insert test value
USE ieq_data;
INSERT INTO ieq_table (Temperature, RH, Illuminance, Date, Time, DeviceID, GatewayID)
VALUES (25.6,67,278,'2020-10-04','20:43:10','DEV000','GWY000');

--Delete all records
USE ieq_data;
DELETE FROM ieq_table;

--Combine Date and Time to Datetime
ALTER TABLE ieq_table
ADD COLUMN Datetime DATETIME AFTER Time;
UPDATE ieq_table SET Datetime = concat(Date,', ',Time);