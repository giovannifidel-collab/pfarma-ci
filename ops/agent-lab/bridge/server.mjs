#!/usr/bin/env node

import http from 'node:http';
import crypto from 'node:crypto';
import { agentIds, getAgent, closeAll } from '../standard/index.mjs';

const HOST=process.env.HIVE_AGENT_BRIDGE_HOST||'127.0.0.1';
const PORT=Number(process.env.HIVE_AGENT_BRIDGE_PORT||9240);
const TOKEN=String(process.env.HIVE_AGENT_BRIDGE_TOKEN||'');
const MAX_BODY=256*1024;
const MAX_ATTEMPTS=Math.max(1,Math.min(Number(process.env.HIVE_AGENT_BRIDGE_ATTEMPTS||2),4));
const locks=new Map();

if(!TOKEN||TOKEN.length<32){
  console.error('ERROR: HIVE_AGENT_BRIDGE_TOKEN must contain at least 32 characters');
  process.exit(78);
}

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const json=(res,status,data)=>{
  const body=JSON.stringify(data);
  res.writeHead(status,{'content-type':'application/json; charset=utf-8','content-length':Buffer.byteLength(body),'cache-control':'no-store'});
  res.end(body);
};

function authorized(req){
  const raw=String(req.headers.authorization||'').replace(/^Bearer\s+/i,'');
  if(!raw||raw.length!==TOKEN.length)return false;
  return crypto.timingSafeEqual(Buffer.from(raw),Buffer.from(TOKEN));
}

async function readJson(req){
  let size=0;const chunks=[];
  for await(const chunk of req){
    size+=chunk.length;
    if(size>MAX_BODY)throw Object.assign(new Error('request too large'),{status:413});
    chunks.push(chunk);
  }
  if(!chunks.length)return {};
  try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}
  catch{throw Object.assign(new Error('invalid json'),{status:400});}
}

async function withAgentLock(id,fn){
  const prior=locks.get(id)||Promise.resolve();
  let release;
  const next=new Promise(r=>{release=r});
  locks.set(id,prior.then(()=>next));
  await prior;
  try{return await fn();}
  finally{release();if(locks.get(id)===next)locks.delete(id);}
}

async function invoke(id,task,{fresh=true,timeoutMs=null}={}){
  const agent=getAgent(id);
  const trace=[];
  let last={status:'error',text:'BRIDGE_NOT_RUN',metadata:{agent_id:id}};
  for(let attempt=1;attempt<=MAX_ATTEMPTS;attempt++){
    const started=Date.now();
    const health=await agent.health();
    trace.push({attempt,stage:'health',status:health.status,text:health.text,latency_ms:Date.now()-started});
    if(health.status==='ok'){
      last=await agent.run(task,{fresh,timeoutMs:timeoutMs||undefined});
      trace.push({attempt,stage:'run',status:last.status,text:String(last.text||'').slice(0,400),latency_ms:Date.now()-started});
      if(last.status==='ok'||last.status==='blocked')break;
    }else{
      last={status:health.status,text:health.text,metadata:health.metadata||{agent_id:id}};
      if(health.status==='blocked')break;
    }
    if(attempt<MAX_ATTEMPTS){
      try{
        const recovery=typeof agent.recover==='function'?await agent.recover(`bridge:${last.text}`):null;
        trace.push({attempt,stage:'recovery',...(recovery||{recovered:false,method:'close-only'})});
        if(!recovery)agent.close();
      }catch(e){trace.push({attempt,stage:'recovery',recovered:false,error:e.message});}
      await sleep(900*attempt);
    }
  }
  return {...last,metadata:{...(last.metadata||{}),bridge:'hive-standard-agent-bridge',bridge_trace:trace}};
}

const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url||'/',`http://${req.headers.host||'localhost'}`);
    if(req.method==='GET'&&url.pathname==='/health'){
      return json(res,200,{ok:true,service:'hive-standard-agent-bridge',schema_version:1,agent_count:agentIds.length});
    }
    if(!authorized(req))return json(res,401,{ok:false,error:'unauthorized'});
    if(req.method==='GET'&&url.pathname==='/agents'){
      return json(res,200,{ok:true,agents:[...agentIds]});
    }
    if(req.method==='POST'&&url.pathname==='/invoke'){
      const body=await readJson(req);
      const id=String(body.agent_id||'').toLowerCase();
      const task=String(body.task||'').trim();
      if(!agentIds.includes(id))return json(res,400,{ok:false,error:`UNKNOWN_AGENT:${id}`});
      if(!task)return json(res,400,{ok:false,error:'task required'});
      const out=await withAgentLock(id,()=>invoke(id,task,{fresh:body.fresh!==false,timeoutMs:Number(body.timeout_ms)||null}));
      return json(res,out.status==='ok'?200:(out.status==='blocked'?423:502),{ok:out.status==='ok',result:out});
    }
    return json(res,404,{ok:false,error:'not found'});
  }catch(e){return json(res,e.status||500,{ok:false,error:e.message||'bridge error'});}
});

server.listen(PORT,HOST,()=>{
  console.log(`HIVE_AGENT_BRIDGE_READY=http://${HOST}:${PORT}`);
  console.log(`AGENTS=${agentIds.join(',')}`);
});

function shutdown(){
  try{closeAll();}catch{}
  server.close(()=>process.exit(0));
  setTimeout(()=>process.exit(0),1500).unref();
}
process.on('SIGINT',shutdown);
process.on('SIGTERM',shutdown);
