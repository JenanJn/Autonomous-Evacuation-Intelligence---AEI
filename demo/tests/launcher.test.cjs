const assert=require('node:assert/strict');
const {selectHost}=require('../../mobile/scripts/start-phone.cjs');
assert.equal(selectHost({'vEthernet':[{family:'IPv4',internal:false,address:'172.20.0.1'}],'Wi-Fi':[{family:'IPv4',internal:false,address:'192.168.1.6'}]}).address,'192.168.1.6');
assert.equal(selectHost({Loopback:[{family:'IPv4',internal:true,address:'127.0.0.1'}]}),undefined);
assert.equal(selectHost({'Wi-Fi':[{family:'IPv4',internal:false,address:'169.254.2.1'}]}),undefined);
console.log('PASS: Wi-Fi address selection, localhost exclusion, invalid link-local exclusion');
