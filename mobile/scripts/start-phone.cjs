/** Local phone launcher. No persistent network or firewall settings are changed. */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
async function available(port) {
  return new Promise(resolve => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)));
  });
}
function selectHost(interfaces=os.networkInterfaces()) {
  const candidates = Object.entries(interfaces).flatMap(([name, addresses]) =>
    (addresses || []).filter(address => address.family === 'IPv4' && !address.internal && !address.address.startsWith('169.254.')).map(address => ({ name, address:address.address })));
  return candidates.find(item => /wi-?fi|wlan|wireless/i.test(item.name)) || candidates.find(item => !/virtual|docker|vethernet|vpn|loopback/i.test(item.name));
}
async function main() {
  if (Number(process.versions.node.split('.')[0]) < 20) throw Error('Install Node.js 20 or later, then run this launcher again.');
  const marker = path.join(root, 'node_modules', 'expo-network', 'package.json');
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
  const dependencies=Object.keys(manifest.dependencies);
  const expoFile=path.join(root,'node_modules','expo','package.json');
  const expectedMajor=manifest.dependencies.expo.match(/[0-9]+/)[0];
  const sdkMatches=fs.existsSync(expoFile)&&JSON.parse(fs.readFileSync(expoFile,'utf8')).version.startsWith(expectedMajor+'.');
  if (!sdkMatches||!fs.existsSync(marker)||!dependencies.every(name=>fs.existsSync(path.join(root,'node_modules',name,'package.json')))) {
    console.log('Installing the project dependencies. Please keep this window open.');
    const result = process.platform === 'win32'
      ? spawnSync('cmd.exe', ['/d', '/s', '/c', 'npm ci'], { cwd:root, stdio:'inherit' })
      : spawnSync('npm', ['ci'], { cwd:root, stdio:'inherit' });
    if (result.error || result.status !== 0) throw Error('Dependency installation failed. Run npm ci inside the mobile folder and check its error.');
  }
  const chosen = selectHost();
  let port = 8081;
  while (port <= 8090 && !(await available(port))) port++;
  if (port > 8090) throw Error('Ports 8081–8090 are busy. Close your earlier Expo server and try again.');
  const environment = { ...process.env, EXPO_NO_DEPENDENCY_VALIDATION:'1' };
  if (chosen) {
    environment.REACT_NATIVE_PACKAGER_HOSTNAME = chosen.address;
    environment.EXPO_PACKAGER_PROXY_URL = `http://${chosen.address}:${port}`;
  } else {
    delete environment.REACT_NATIVE_PACKAGER_HOSTNAME;
    delete environment.EXPO_PACKAGER_PROXY_URL;
    console.log('No usable local IPv4 address was found. Connect your computer to Wi-Fi first.');
  }
  console.log('\nAEI MOBILE · SDK 53\nUse the SDK 53 version of Expo Go on Android.');
  console.log('Phone and computer must be on the same Wi-Fi. Keep this window open.');
  if (chosen) console.log(`QR connection: exp://${chosen.address}:${port}\n`);
  const cli = path.join(root, 'node_modules', 'expo', 'bin', 'cli');
  const child = spawn(process.execPath, [cli, 'start', '--go', '--lan', '--port', String(port)], { cwd:root, env:environment, stdio:'inherit' });
  child.once('error', error => { console.error(error.message); process.exitCode=1; });
  child.once('exit', code => { process.exitCode=code || 0; });
}
if (require.main === module) main().catch(error => { console.error('\n'+error.message); process.exitCode=1; });
module.exports={selectHost};
