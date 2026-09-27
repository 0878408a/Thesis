import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getFullnodeUrl, IotaClient } from '@iota/iota-sdk/client';
import { Secp256k1Keypair } from '@iota/iota-sdk/keypairs/secp256k1';
import { fromBase64 } from '@iota/bcs'; // 用來解碼 base64
import { Transaction } from '@iota/iota-sdk/transactions';

// 以腳本檔案所在目錄解析 .env，避免依賴 process.cwd()
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({
  path: path.resolve(__dirname, '..', '.env'),
});

// 必要的環境變數
const NETWORK = process.env.IOTA_NETWORK;
const PRIVATE_KEY_BASE64 = process.env.IOTA_PRIVATE_KEY_BASE64;
const PACKAGE_ID = process.env.PACKAGE_ID;
const MODULE_NAME = process.env.MOVE_MODULE;
const FUNCTION_NAME = process.env.MOVE_FUNCTION;

if (!NETWORK) throw new Error('Missing IOTA_NETWORK in .env');
if (!PRIVATE_KEY_BASE64) throw new Error('Missing IOTA_PRIVATE_KEY_BASE64 in .env');
if (!PACKAGE_ID) throw new Error('Missing PACKAGE_ID in .env');
if (!MODULE_NAME) throw new Error('Missing MOVE_MODULE in .env');
if (!FUNCTION_NAME) throw new Error('Missing MOVE_FUNCTION in .env');

// timeout helper for long-running RPCs
const IOTA_TIMEOUT_MS = 30_000;
async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, operation: string): Promise<T> {
  let timer: NodeJS.Timeout;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`[IOTA] TIMEOUT: ${operation}`)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeoutPromise]) as T;
  } finally {
    clearTimeout(timer!);
  }
}

// 去掉私鑰的 prefix（第一個 byte 為演算法識別）
const rawKey = fromBase64(PRIVATE_KEY_BASE64).slice(1);
const keypair = Secp256k1Keypair.fromSecretKey(rawKey);
const sender = keypair.getPublicKey().toIotaAddress();

console.log('[IOTA] START');
console.log('[IOTA] NETWORK:', NETWORK);
console.log('[IOTA] PACKAGE_ID:', PACKAGE_ID);
console.log('[IOTA] MODULE_NAME:', MODULE_NAME);
console.log('[IOTA] FUNCTION_NAME:', FUNCTION_NAME);

console.log('[IOTA] KEYPAIR OK');

// 建立 IotaClient
const client = new IotaClient({ url: getFullnodeUrl(NETWORK as any) });
console.log('[IOTA] CLIENT CREATED');
console.log('[IOTA] SENDER:', sender);

// 將 UTF-8 字串轉成 vector<u8>
function strToVectorU8(str: string): number[] {
  return Array.from(new TextEncoder().encode(str));
}

async function main() {
  // 取得 CLI 參數（僅接受 9 個參數）
  const argsPassed = process.argv.slice(2);
  if (argsPassed.length !== 9) {
    throw new Error('請依序傳入 9 個參數: metadata_algorithm metadata_signature firmware_algorithm firmware_signature firmware_size release_date manufacturer_id device_type firmware_version');
  }

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
  ] = argsPassed;

  // 建立交易
  const tx = new Transaction();
  console.log('[IOTA] TRANSACTION CREATED');

  const moveArgs = [
    tx.pure('vector<u8>', strToVectorU8(metadata_algorithm)),
    tx.pure('vector<u8>', Array.from(fromBase64(metadata_signature))),
    tx.pure('vector<u8>', strToVectorU8(firmware_algorithm)),
    tx.pure('vector<u8>', Array.from(fromBase64(firmware_signature))),
    tx.pure('u64', BigInt(firmware_size)),
    tx.pure('u64', BigInt(release_date)),
    tx.pure('vector<u8>', strToVectorU8(manufacturer_id)),
    tx.pure('vector<u8>', strToVectorU8(device_type)),
    tx.pure('vector<u8>', strToVectorU8(firmware_version)),
  ];

  tx.moveCall({ target: `${PACKAGE_ID}::${MODULE_NAME}::${FUNCTION_NAME}`, arguments: moveArgs });
  console.log('[IOTA] MOVE CALL CREATED');

  // 取得 owned objects
  console.log('[IOTA] BEFORE getOwnedObjects');
  const ownedObjects = await withTimeout(client.getOwnedObjects({ owner: sender }), IOTA_TIMEOUT_MS, 'getOwnedObjects');
  console.log('[IOTA] AFTER getOwnedObjects');

  // 取得每個 object 的內容
  console.log('[IOTA] BEFORE getObject');
  const detailedObjects = await Promise.all(
    ownedObjects.data.map(obj =>
      withTimeout(
        client.getObject({ id: obj.data.objectId, options: { showContent: true } }),
        IOTA_TIMEOUT_MS,
        `getObject:${obj.data.objectId}`
      )
    )
  );
  console.log('[IOTA] AFTER getObject');

  // 篩選 gas coin
  const gasCoin = detailedObjects
    .map(o => o.data)
    .find(o =>
      o?.content?.type?.includes('coin::Coin') &&
      o?.content?.fields?.balance !== undefined &&
      BigInt(o.content.fields.balance) > 1_000_000n
    );

  if (!gasCoin) {
    throw new Error('沒有足夠餘額的 gas coin 可用');
  }

  const gasCoinId = gasCoin.objectId;
  console.log('[IOTA] GAS COIN FOUND:', gasCoinId);

  // 執行並簽署交易
  console.log('[IOTA] BEFORE signAndExecuteTransaction');
  const result = await withTimeout(
    client.signAndExecuteTransaction({
      transaction: tx,
      signer: keypair,
      gasPayment: [gasCoinId],
      options: { showEffects: true, showEvents: true },
    }),
    IOTA_TIMEOUT_MS,
    'signAndExecuteTransaction'
  );
  console.log('[IOTA] AFTER signAndExecuteTransaction');

  console.log('[IOTA] TRANSACTION RESULT RECEIVED');

  const createdObject = result.effects?.created?.[0]?.reference?.objectId;
  if (createdObject) {
    console.log(`OBJECT_ID:${createdObject}`);
    return;
  }

  throw new Error('No objectId returned');
}

// main error handling per requirement
main().catch(error => {
  console.error('[IOTA] ERROR:', error);
  process.exit(1);
});
