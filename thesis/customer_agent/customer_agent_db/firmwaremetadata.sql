-- --------------------------------------------------------
-- 主機:                           127.0.0.1
-- 伺服器版本:                        11.7.2-MariaDB - mariadb.org binary distribution
-- 伺服器作業系統:                      Win64
-- HeidiSQL 版本:                  12.10.0.7000
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- 傾印 customer_database 的資料庫結構
CREATE DATABASE IF NOT EXISTS `customer_database` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;
USE `customer_database`;

-- 傾印  資料表 customer_database.firmwaremetadata 結構
CREATE TABLE IF NOT EXISTS `firmwaremetadata` (
  `object_id` char(66) NOT NULL DEFAULT '',
  `metadata_signature` varbinary(512) NOT NULL,
  `metadata_signature_algorithm` varchar(255) NOT NULL,
  `firmware_signature` varbinary(512) NOT NULL,
  `firmware_signature_algorithm` varchar(255) NOT NULL,
  `firmware_size` bigint(20) unsigned NOT NULL,
  `release_date` bigint(20) NOT NULL,
  `manufacturer_id` char(36) NOT NULL,
  `device_type` varchar(100) NOT NULL,
  `firmware_version` varchar(50) NOT NULL,
  `firmware_data` longblob NOT NULL,
  PRIMARY KEY (`object_id`),
  UNIQUE KEY `object_id` (`object_id`),
  UNIQUE KEY `uq_mfr_dev_fwm` (`manufacturer_id`,`device_type`,`firmware_version`),
  KEY `FK_notify_firmwaremetadata_device_record` (`manufacturer_id`,`device_type`),
  CONSTRAINT `FK_notify_firmwaremetadata_device_record` FOREIGN KEY (`manufacturer_id`, `device_type`) REFERENCES `device` (`manufacturer_id`, `device_type`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 取消選取資料匯出。

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
