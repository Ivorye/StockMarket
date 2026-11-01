-- stockshare 数据库结构定义（仅表结构，不含数据）
-- 由 mysqldump --no-data 从本地 MySQL 8.0.36 导出，共 16 张表：
--   st_announcement / st_api_request_state / st_backtest_run / st_backtest_summary
--   st_backtest_trade / st_basic / st_daily / st_daily_signal / st_execution_status
--   st_suspect_stock / stock_share / stock_share_seq / stocks / stocks_seq / user / user_seq
-- 说明：按股代码分表的 gp{symbol} 由 loadStocks.py:createStockTable() 运行时动态创建，不在本文件内。

-- MySQL dump 10.13  Distrib 8.0.36, for Win64 (x86_64)
--
-- Host: localhost    Database: stockshare
-- ------------------------------------------------------
-- Server version	8.0.36

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `stockshare`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `stockshare` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `stockshare`;

--
-- Table structure for table `st_announcement`
--

DROP TABLE IF EXISTS `st_announcement`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_announcement` (
  `id` int NOT NULL AUTO_INCREMENT,
  `st_code` varchar(12) NOT NULL COMMENT '股票代码 000001.SZ',
  `ann_date` varchar(8) NOT NULL COMMENT '公告日期 YYYYMMDD',
  `title` varchar(255) NOT NULL COMMENT '公告标题',
  `art_code` varchar(32) NOT NULL COMMENT '东财公告编号',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_art` (`st_code`,`art_code`),
  KEY `idx_code_date` (`st_code`,`ann_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_api_request_state`
--

DROP TABLE IF EXISTS `st_api_request_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_api_request_state` (
  `api_name` varchar(64) NOT NULL,
  `next_allowed_at` datetime NOT NULL,
  `last_success_date` varchar(8) DEFAULT NULL,
  PRIMARY KEY (`api_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_backtest_run`
--

DROP TABLE IF EXISTS `st_backtest_run`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_backtest_run` (
  `run_id` varchar(36) NOT NULL,
  `strategy` varchar(64) NOT NULL,
  `start_date` varchar(8) NOT NULL,
  `end_date` varchar(8) NOT NULL,
  `window_days` int NOT NULL,
  `horizons` varchar(32) NOT NULL,
  `min_gain_pct` double NOT NULL,
  `min_r_squared` double NOT NULL,
  `min_up_ratio` double NOT NULL,
  `max_drawdown_pct` double NOT NULL,
  `status` varchar(16) NOT NULL,
  `trade_count` int NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`run_id`),
  KEY `idx_strategy_created` (`strategy`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_backtest_summary`
--

DROP TABLE IF EXISTS `st_backtest_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_backtest_summary` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(36) NOT NULL,
  `period_type` varchar(16) NOT NULL,
  `period_value` varchar(16) NOT NULL,
  `horizon` int NOT NULL,
  `signals` int NOT NULL,
  `win_rate_pct` double NOT NULL,
  `avg_return_pct` double NOT NULL,
  `median_return_pct` double NOT NULL,
  `p25_return_pct` double NOT NULL,
  `p75_return_pct` double NOT NULL,
  `avg_mfe_pct` double NOT NULL,
  `median_mfe_pct` double NOT NULL,
  `avg_mae_pct` double NOT NULL,
  `median_mae_pct` double NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_run_period_horizon` (`run_id`,`period_type`,`period_value`,`horizon`),
  CONSTRAINT `fk_backtest_summary_run` FOREIGN KEY (`run_id`) REFERENCES `st_backtest_run` (`run_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_backtest_trade`
--

DROP TABLE IF EXISTS `st_backtest_trade`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_backtest_trade` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(36) NOT NULL,
  `ts_code` varchar(12) NOT NULL,
  `signal_date` varchar(8) NOT NULL,
  `entry_date` varchar(8) NOT NULL,
  `entry_open` double NOT NULL,
  `horizon` int NOT NULL,
  `exit_date` varchar(8) NOT NULL,
  `exit_close` double NOT NULL,
  `return_pct` double NOT NULL,
  `mfe_pct` double NOT NULL,
  `mae_pct` double NOT NULL,
  `signal_gain_pct` double NOT NULL,
  `signal_r_squared` double NOT NULL,
  `signal_up_ratio` double NOT NULL,
  `signal_max_drawdown_pct` double NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_run_signal_horizon` (`run_id`,`ts_code`,`signal_date`,`horizon`),
  KEY `idx_run_horizon` (`run_id`,`horizon`),
  CONSTRAINT `fk_backtest_trade_run` FOREIGN KEY (`run_id`) REFERENCES `st_backtest_run` (`run_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_basic`
--

DROP TABLE IF EXISTS `st_basic`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_basic` (
  `ts_code` varchar(12) NOT NULL,
  `symbol` varchar(6) DEFAULT NULL,
  `name` varchar(50) DEFAULT NULL,
  `area` varchar(10) DEFAULT NULL,
  `list_date` varchar(8) DEFAULT NULL,
  PRIMARY KEY (`ts_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_daily`
--

DROP TABLE IF EXISTS `st_daily`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_daily` (
  `ts_code` varchar(12) NOT NULL,
  `symbol` varchar(6) NOT NULL,
  `trade_date` varchar(8) NOT NULL,
  `openp` float DEFAULT NULL,
  `high` float DEFAULT NULL,
  `low` float DEFAULT NULL,
  `closep` float DEFAULT NULL,
  `preclose` float DEFAULT NULL,
  `changes` float DEFAULT NULL,
  `pct_chg` float DEFAULT NULL,
  `vol` float DEFAULT NULL,
  `amount` float DEFAULT NULL,
  PRIMARY KEY (`ts_code`,`trade_date`),
  KEY `idx_trade_date` (`trade_date`),
  KEY `idx_symbol` (`symbol`),
  KEY `idx_trade_date_ts_code` (`trade_date`,`ts_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_daily_signal`
--

DROP TABLE IF EXISTS `st_daily_signal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_daily_signal` (
  `id` int NOT NULL AUTO_INCREMENT,
  `trade_date` varchar(8) NOT NULL,
  `st_code` varchar(12) NOT NULL,
  `strategy` varchar(50) NOT NULL DEFAULT 'default',
  `closePrice` float DEFAULT NULL,
  `pct_chg` float DEFAULT NULL,
  `vol` float DEFAULT NULL,
  `prev_vol` float DEFAULT NULL,
  `vol_ratio` float DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_date_code_strategy` (`trade_date`,`st_code`,`strategy`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_execution_status`
--

DROP TABLE IF EXISTS `st_execution_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_execution_status` (
  `task_name` varchar(50) NOT NULL,
  `exec_date` varchar(8) DEFAULT NULL,
  `source` varchar(10) DEFAULT 'system' COMMENT '更新来源：manual=人工，system=系统自动',
  `status` varchar(1) DEFAULT 'N',
  PRIMARY KEY (`task_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `st_suspect_stock`
--

DROP TABLE IF EXISTS `st_suspect_stock`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `st_suspect_stock` (
  `trade_date` varchar(8) NOT NULL COMMENT '扫描基准日',
  `st_code` varchar(12) NOT NULL COMMENT '股票代码',
  `name` varchar(50) DEFAULT NULL,
  `gain_pct` float DEFAULT NULL COMMENT '30日涨幅%',
  `r_squared` float DEFAULT NULL COMMENT '30日趋势R2',
  `max_drawdown_pct` float DEFAULT NULL COMMENT '30日最大回撤%',
  `up_ratio` float DEFAULT NULL COMMENT '上涨日占比%',
  `avg_turnover_pct` float DEFAULT NULL COMMENT '30日日均换手率%',
  `avg_amount_yi` float DEFAULT NULL COMMENT '30日日均成交额(亿元)',
  `float_shares` double DEFAULT NULL COMMENT '流通股本(股)',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`trade_date`,`st_code`),
  KEY `idx_trade_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `stock_share`
--

DROP TABLE IF EXISTS `stock_share`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stock_share` (
  `id` int NOT NULL,
  `code` varchar(255) DEFAULT NULL,
  `fullname` varchar(255) DEFAULT NULL,
  `list_date` varchar(255) DEFAULT NULL,
  `symbol` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `stock_share_seq`
--

DROP TABLE IF EXISTS `stock_share_seq`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stock_share_seq` (
  `next_val` bigint DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `stocks`
--

DROP TABLE IF EXISTS `stocks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stocks` (
  `id` int NOT NULL,
  `symbol` varchar(6) NOT NULL,
  `name` varchar(50) DEFAULT '',
  `st_code` varchar(9) NOT NULL,
  `fullname` varchar(50) NOT NULL,
  `list_date` varchar(8) NOT NULL,
  `stcode` varchar(255) DEFAULT NULL,
  `industry` varchar(50) DEFAULT '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ts_code_UNIQUE` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `stocks_seq`
--

DROP TABLE IF EXISTS `stocks_seq`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stocks_seq` (
  `next_val` bigint DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` int NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_seq`
--

DROP TABLE IF EXISTS `user_seq`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_seq` (
  `next_val` bigint DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping routines for database 'stockshare'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-01 21:32:33
