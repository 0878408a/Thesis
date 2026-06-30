// Move 的模組宣告，完整名稱為 firmware_notify::firmware_module
// 需對應 Move.toml 中定義的 name 與 addresses
module firmware_notify::firmware_module {
    // 導入 IOTA 提供的 event 模組，用於在交易中發送事件供外部查詢
    use iota::event;
    /// 資源導向（Resource-Oriented）：把「真實世界資產」直接映射為語言層面的資源（resource），確保「不被複製、不被遺失」
    /// Resource 是 Move 最核心的抽象，對應鏈上「只能有一份、不能無中生有、不能私自銷毀」的資產（如代幣、NFT、固有物件）。
    /// 在宣告 struct 時，加上 has key、has store、has drop、has copy 能力標記：
    /// has key：允許 struct 作為全域儲存的key值，代表其可以被儲存在全域狀態中。
    /// has store：可以被作為欄位嵌入其他具有 key 能力的 struct 中。
    /// has drop、has copy：允許 struct 被丟棄（即在不使用的情況下自動清除）、允許 struct 被複製。
    /// 
    /// 定義一個 FirmwareEvent struct，具有 copy + drop 能力，可用於事件傳送。
    /// event struct 中不能包含 UID，因為 UID 須保證唯一，無法具備 copy/drop 能力
    /// 發送事件的目的，是讓外部 SDK 客戶端可快速知道有哪些新 firmware 被上鏈，
    /// 進一步再透過其他 API 查詢詳細內容。
    public struct FirmwareEvent has copy, drop {
        object_id: vector<u8>,           // 對應 FirmwareMetadata 的 UID，經轉換為 bytes，供外部辨識查詢
        manufacturer_id: vector<u8>,     // 製造商識別碼
        device_type: vector<u8>,         // 裝置型號（如 ESP32）
        firmware_version: vector<u8>,    // 韌體版本（如 v1.0）
    }

    /// 定義 FirmwareMetadata struct，此為主要儲存上鏈資訊的物件
    /// 加上 key, store 能力，使其可儲存於全域狀態（object space）
    /// 並允許透過 object ID 查詢持有人與內容。
    public struct FirmwareMetadata has key, store {
        id: object::UID,                             // 全域唯一識別碼，由 object::new(ctx) 建立
        metadata_signature_algorithm: vector<u8>,    // Metadata 簽章使用之演算法（如 rsa 或 ecdsa）
        metadata_signature: vector<u8>,              // Metadata 的簽章值
        firmware_signature_algorithm: vector<u8>,    // 韌體主體的簽章演算法
        firmware_signature: vector<u8>,              // 韌體本體簽章值
        firmware_size: u64,                          // 韌體檔案大小（單位：bytes）
        release_date: u64,                           // 發布時間戳（NTP timestamp）
        manufacturer_id: vector<u8>,                 // 製造商 ID（UUID 或類似識別字串）
        device_type: vector<u8>,                     // 裝置型號（如 esp32）
        firmware_version: vector<u8>,                // 韌體版本（如 v1.0、v1.2.3）
    }

    /// 在 Move 中，無法直接將 FirmwareMetadata 當作參數傳給 entry function。
    /// 所以只能把 struct 的每一個欄位拆開來作為獨立參數，然後在 function 內手動組裝起來。
    /// Move 是一種安全性為重的語言，為了明確資料結構與行為：
    /// 沒有 tuple / map 當作 function 引數的支援，必須明確列出每個參數型別與名稱
    /// 
    /// 公開的 entry function，可被發送交易呼叫（例如透過 TypeScript SDK）
    /// 用來將一筆新的韌體 metadata 上鏈，並同步發出事件通知。
    /// 可用於建立新物件（object::new）與取得呼叫者帳號（ctx.sender()）
    public entry fun publish(
        metadata_signature_algorithm: vector<u8>,
        metadata_signature: vector<u8>,
        firmware_signature_algorithm: vector<u8>,
        firmware_signature: vector<u8>,
        firmware_size: u64,
        release_date: u64,
        manufacturer_id: vector<u8>,
        device_type: vector<u8>,
        firmware_version: vector<u8>,
        ctx: &mut tx_context::TxContext,
        // 傳入一個 「可變的 Transaction Context reference」，可以透過 ctx：
        //
        //    建立物件（產生全域唯一識別碼，附加到 struct 上）id: object::new(ctx)
        //
        //    取得交易發送者 ctx.sender()
        //
        //    將物件儲存到帳戶下(將 metadata struct 上鏈儲存到發送者帳戶下) transfer::public_transfer(obj, ctx.sender())
        //
        // 在 Move 語言中，&mut 是一種可變參考（mutable reference），它表示「你可以透過這個參考修改原始值」
        // ctx 為 IOTA 自動注入的 Transaction Context（tx_context::TxContext），struct TxContext 包含以下欄位:
        //      
        //      sender: address
        //      簽署當前交易的使用者地址
        //
        //      tx_hash: vector<u8>,
        //      目前交易的雜湊值
        //
        //      epoch: u64,
        //      current epoch number
        //
        //      epoch_timestamp_ms: u64,
        //      Timestamp that the epoch started at
        //
        //      ids_created: u64,
        //      Counter recording the number of fresh id's created while executing this transaction.
        //      Always 0 at the start of a transaction
    ) {
        // 建立 FirmwareMetadata 物件，並生成唯一 UID 作為識別
        // metadata struct 中使用 UID，因此 struct 本身無法具備 copy/drop 能力 (因為 UID 保證唯一)
        let metadata = FirmwareMetadata {
            id: object::new(ctx),                           // 建立唯一 UID（與 ctx 關聯）
            metadata_signature_algorithm,
            metadata_signature,
            firmware_signature_algorithm,
            firmware_signature,
            firmware_size,
            release_date,
            manufacturer_id: copy manufacturer_id,          // 被使用兩次，因此需 copy
            device_type: copy device_type,                  // 被使用兩次，因此需 copy
            firmware_version: copy firmware_version,        // 被使用兩次，因此需 copy
            // 在 Move 中，若一個變數被多次使用，且其類型沒有 copy 能力，則必須顯式地使用 copy 關鍵字來複製該變數
        };

        // 將 UID 轉為 bytes，方便存入 event struct 中（event 不支援 UID 類型）
        // & 是用來取得 metadata 物件中 id 欄位的參考（reference）
        let object_id = object::uid_to_bytes(&metadata.id);

        // 實際上鏈：將 FirmwareMetadata 物件儲存在發送者帳戶下
        transfer::public_transfer(metadata, ctx.sender());

        // 建立 FirmwareEvent event 物件，用於告知外部有一筆新的韌體上鏈
        // 可由客戶端 queryEvents 訂閱接收，再據此查詢對應的物件內容
        let evt = FirmwareEvent {
            object_id,
            manufacturer_id,
            device_type,
            firmware_version,
        };

        // 發送事件（僅作為通知用途，不佔用鏈上儲存空間）
        event::emit(evt);
    }
}
