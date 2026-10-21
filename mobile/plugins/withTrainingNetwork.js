// Optional cleartext HTTP for trusted classroom training networks only.
const {withAndroidManifest}=require('@expo/config-plugins');
module.exports=config=>withAndroidManifest(config,mod=>{
 if(process.env.AEI_ALLOW_INSECURE_TRAINING==='1')mod.modResults.manifest.application[0].$['android:usesCleartextTraffic']='true';
 return mod;
});
