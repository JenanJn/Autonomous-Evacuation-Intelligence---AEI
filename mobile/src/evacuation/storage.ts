import * as SQLite from 'expo-sqlite';
import type { Area } from './engine';
let connection: Promise<SQLite.SQLiteDatabase> | undefined;
async function database() {
  if (!connection) connection = SQLite.openDatabaseAsync('aei-offline.db').then(async db => {
    await db.execAsync('CREATE TABLE IF NOT EXISTS packages (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)');
    return db;
  });
  return connection;
}
export async function loadArea(): Promise<Area | null> {
  const row = await (await database()).getFirstAsync<{data:string}>('SELECT data FROM packages WHERE id=1');
  if (!row) return null;
  const area = JSON.parse(row.data) as Area;
  if (!area.simulated || !Array.isArray(area.nodes) || !Array.isArray(area.roads)) throw Error('Invalid offline package');
  return area;
}
export async function saveArea(area: Area) {
  await (await database()).runAsync('INSERT OR REPLACE INTO packages(id,data) VALUES(1,?)', JSON.stringify(area));
}
