CREATE DATABASE IF NOT EXISTS `stockshare` DEFAULT CHARACTER SET utf8mb4;

USE `stockshare`;

DROP TABLE IF EXISTS `stocks`;

CREATE TABLE `stocks` (
  `id` INT NOT NULL,
  `symbol` VARCHAR(10) NOT NULL COMMENT '股票代码，如 000001',
  `st_code` VARCHAR(20) NOT NULL COMMENT 'Tushare代码，如 000001.SZ',
  `fullname` VARCHAR(100) DEFAULT NULL COMMENT '股票全称',
  `list_date` VARCHAR(8) DEFAULT NULL COMMENT '上市日期，格式 YYYYMMDD',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_symbol` (`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基本信息表(新代码库)';

DROP TABLE IF EXISTS `st_basic`;

CREATE TABLE `st_basic` (
  `ts_code` VARCHAR(20) NOT NULL COMMENT 'Tushare代码，如 000001.SZ',
  `symbol` VARCHAR(10) DEFAULT NULL COMMENT '股票代码，如 000001',
  `name` VARCHAR(50) DEFAULT NULL COMMENT '股票名称',
  `area` VARCHAR(20) DEFAULT NULL COMMENT '地域',
  `list_date` VARCHAR(8) DEFAULT NULL COMMENT '上市日期，格式 YYYYMMDD',
  PRIMARY KEY (`ts_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基本信息表(旧代码库)';
