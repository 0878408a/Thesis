-- --------------------------------------------------------
-- 主機:                           127.0.0.1
-- 伺服器版本:                        12.2.2-MariaDB - MariaDB Server
-- 伺服器作業系統:                      Win64
-- HeidiSQL 版本:                  12.14.0.7165
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

-- 傾印  資料表 customer_database.customer_device 結構
CREATE TABLE IF NOT EXISTS `customer_device` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `manufacturer_id` char(36) NOT NULL,
  `device_type` varchar(100) NOT NULL,
  `firmware_version` varchar(50) NOT NULL,
  `customer_id` char(36) NOT NULL,
  `update_method` varchar(16) NOT NULL,
  `ip_address` varchar(64) NOT NULL,
  `mac_address` varchar(17) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_device_owner_customer_record` (`customer_id`),
  KEY `manufacturer_id_device_type` (`manufacturer_id`,`device_type`),
  KEY `FK_customer_device_firmwaremetadata` (`firmware_version`),
  CONSTRAINT `FK_customer_device_device` FOREIGN KEY (`manufacturer_id`, `device_type`) REFERENCES `device` (`manufacturer_id`, `device_type`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_customer_device_firmwaremetadata` FOREIGN KEY (`firmware_version`) REFERENCES `firmwaremetadata` (`firmware_version`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_device_owner_customer_record` FOREIGN KEY (`customer_id`) REFERENCES `customer` (`customer_id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 正在傾印表格  customer_database.customer_device 的資料：~1 rows (近似值)
DELETE FROM `customer_device`;
INSERT INTO `customer_device` (`id`, `manufacturer_id`, `device_type`, `firmware_version`, `customer_id`, `update_method`, `ip_address`, `mac_address`) VALUES
	(1, '123e4567-e89b-12d3-a456-426614174000', 'esp32', 'v1.11', '3e01e6a7-1c25-4a5e-97c5-92ec5abfd10c', 'https', '10.168.233.163', 'e8:68:e7:23:71:d8');

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
