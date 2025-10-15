import { getFullnodeUrl, IotaClient } from '@iota/iota-sdk/client';
import { Secp256k1Keypair } from '@iota/iota-sdk/keypairs/secp256k1';
import { fromB64 } from '@iota/bcs'; // 用來解碼 base64
import { Transaction } from '@iota/iota-sdk/transactions';

// base64 編碼的私鑰字串（前綴包含算法識別碼）
const BASE64_PRIVATE_KEY = 'AW8+XT3NFjeh91PMrRg0N0JZdLkc3BaF8rWMO0s6Uvfz';
// 去掉 prefix，第一個 byte 是私鑰算法類型的識別碼
const rawKey = fromB64(BASE64_PRIVATE_KEY).slice(1);

// 建立 secp256k1 keypair
const keypair = Secp256k1Keypair.fromSecretKey(rawKey);
// 從公鑰取得 iota 帳戶地址
const sender = keypair.getPublicKey().toIotaAddress();

// 建立 IotaClient 連線物件，指定測試網
const client = new IotaClient({
  url: getFullnodeUrl('testnet'),
});

// 將 UTF-8 字串轉成 vector<u8>
function strToVectorU8(str: string): number[] {
  return Array.from(new TextEncoder().encode(str));
}

// 主程式：發送交易並執行 move 模組
async function main() {

    // 接收 django 端 9 個須上鏈的參數
    const [
      metadata_algorithm,
      metadata_signature,
      firmware_algorithm,
      firmware_signature,
      firmware_size,
      release_date,
      manufacturer_id,
      device_type,
      firmware_version,
    ] = process.argv.slice(2); // 排除前面那兩個 npx tsx 和 submit_firmware.ts 參數
    
    // 檢查參數數量是否正確
    // 加上 npx tsx 和 submit_firmware.ts，共 11 個參數
    if (process.argv.length < 11) {
      throw new Error('請依序傳入 9 個參數: metadata_algorithm metadata_signature firmware_algorithm firmware_signature firmware_size release_date manufacturer_id device_type firmware_version');
    }

    console.log('Sender address:', sender);

    const tx = new Transaction(); // 建立新交易

    // Move 模組資訊
    const PACKAGE_ID = '0x08e70252b9d1ecd72456899d02450fd2f76cba1993b6d291d7c7094681a96933';
    const MODULE_NAME = 'firmware_module';
    const FUNCTION_NAME = 'publish';

    // 準備呼叫 publish 所需的參數
    const args = [
        tx.pure('vector<u8>', strToVectorU8(metadata_algorithm)),
        tx.pure('vector<u8>', Array.from(fromB64(metadata_signature))), 
        // fromB64(...): 接收字串後還原 base64 成 bytes，再用 Array.from(...) 轉成 vector<u8>
        tx.pure('vector<u8>', strToVectorU8(firmware_algorithm)),
        tx.pure('vector<u8>', Array.from(fromB64(firmware_signature))),
        tx.pure('u64', BigInt(firmware_size)), // 直接轉成 64-bit 整數，不需要編碼成 bytes
        tx.pure('u64', BigInt(release_date)),  // 直接轉成 64-bit 整數，不需要編碼成 bytes
        tx.pure('vector<u8>', strToVectorU8(manufacturer_id)),
        tx.pure('vector<u8>', strToVectorU8(device_type)),
        tx.pure('vector<u8>', strToVectorU8(firmware_version)),
    ];


    // console.log('Args prepared for moveCall:', args);

    // 配置呼叫目標模組與函式
    tx.moveCall({
        target: `${PACKAGE_ID}::${MODULE_NAME}::${FUNCTION_NAME}`,
        arguments: args,
    });

    // 查詢所有擁有的物件 ID（僅 metadata）
    // 告訴 IotaClient：查一下 sender 帳戶擁有什麼資產（物件）？
    // 這裡拿到的物件只有 ID 和類型
    const ownedObjects = await client.getOwnedObjects({ owner: sender });

    // 查詢每個資產物件的完整內容（showContent 必須設為 true）
    // Promise.all([...])	是一組 Promise 的陣列，同時查很多物件（非同步），等全部完成再回傳結果
    /*
        promise 陣列的內容:

        [
          client.getObject({ id: '0x123', options: { showContent: true } }),
          client.getObject({ id: '0x456', options: { showContent: true } })
        ]
    */
    // ownedObjects.data: 所有 sender 帳戶擁有的物件列表（每一筆都有個 objectId）
    // .map(...): 對每一個物件，呼叫 client.getObject(...) 去取得詳細內容
    const detailedObjects = await Promise.all(
      // obj => 的意思是傳入一個物件 obj，
      // 然後回傳 client.getObject(...) 呼叫的結果（這是一個 Promise）
      ownedObjects.data.map(obj =>
        client.getObject({
          id: obj.data.objectId,
          options: { showContent: true }, 
          // 告訴 IOTA 節點：需要這個物件裡的內容，不只 ID，要把 balance 顯示出來
        })
      )
    );

    // 篩選出有效的 coin::Coin 物件，且餘額足夠
    // 傳入 obj 將 detailedObjects 陣列中的每一個物件 obj.data 取出來:
    /*
        {
          data: {
            objectId: '0xabc123...',
            content: {
              type: '0x2::coin::Coin<0x2::aptos_coin::AptosCoin>',
              fields: {
                balance: "12345678"
              }
            }
          }
        }
    */
    const gasCoin = detailedObjects
      .map(obj => obj.data)
      .find(obj =>                                      // 傳入 obj 取出每一個物件進行篩選
        obj?.content?.type?.includes('coin::Coin') &&   // 檢查物件類型是否為 coin::Coin
        obj?.content?.fields?.balance !== undefined &&  // 檢查餘額是否存在
        BigInt(obj.content.fields.balance) > 1_000_000n // 檢查餘額是否大於 1_000_000 (1 IOTA)
      // 這裡的 1_000_000n 是 BigInt 型別的數字，表示 1 IOTA
      );

    if (!gasCoin) {
      throw new Error('沒有足夠餘額的 gas coin 可用');
    }

    const gasCoinId = gasCoin.objectId;

    // 執行交易並簽名，送出至 IOTA 網路
    const result = await client.signAndExecuteTransaction({
        transaction: tx,
        signer: keypair,
        gasPayment: [gasCoinId],
        options: {
        showEffects: true, // 顯示交易影響（例如物件 ID）
        showEvents: true,  // 顯示交易事件（如果模組有 emit）
        },
  });

  // 輸出結果（縮排 2 格，格式化為 JSON）
  console.log('Transaction Result:', JSON.stringify(result, null, 2));
  /*
    {
      "effects": {                            // 交易影響
        "created": [                          // 新建立的物件列表  
          {
            "reference": {
              "objectId": "0x1234567890abcdef",
              "version": 1,
              "type": "0x2::coin::Coin<0x2::aptos_coin::AptosCoin>"
            }
          }
        ],
        ...
      },
      ...
    }
  */
  const createdObject = result.effects?.created?.[0]?.reference?.objectId; 
  //[0] 取第一個物件
  // reference.objectId：該物件的唯一識別碼（Move 上鏈的 UID）
  if (createdObject) {
    console.log(`OBJECT_ID:${createdObject}`);
  } else {
    console.error('No objectId returned');
    process.exit(1);
  }
}

// 執行主流程（錯誤時輸出）
main().catch(console.error);
