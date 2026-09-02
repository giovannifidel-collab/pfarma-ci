#!/usr/bin/env node

import http from 'node:http';
import crypto from 'node:crypto';
import { agentIds, getAgent, closeAll } from '../standard/index.mjs';

const HOST=process.env.HIVE_AGENT_BRIDGE_HOST||'127.0.0.1';
const PORT=Number(process.env.HIVE_AGENT_BRIDGE_PORT||9240);
const TOKEN=String(process.env.HIVE_AGENT_BRIDGE_TOKEN||'');
const MAX_BODY=256*1024;
const MAX_ATTEMPTS=Math.max(1,Math.min(Number(process.env.HIVE_AGENT_BRIDGE_ATTEMPTS||2),4));
const JOB_TTL_MS=Math.max(300000,Math.min(Number(process.env.HIVE_AGENT_BRIDGE_JOB_TTL_MS||3600000),86400000));
const locks=new Map();
const jobs=new Map();

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
  const gate=new Promise(r=>{release=r});
  const chain=prior.then(()=>gate);
  locks.set(id,chain);
  await prior;
  try{return await fn();}
  finally{
    release();
    if(locks.get(id)===chain)locks.delete(id);
  }
}

async function invoke(id,task,{fresh=true,timeoutMs=null}={}){
  const agent=getAgent(id);
  const trace=[];
  let last={status:'error',text:'BRIDGE_NOT_RUN',metadata:{agent_id:id}};
  for(let attempt=1;attempt<=MAX_ATTEMPTS;attempt++){
    const started=Date.now();
    const health=await agent.health();
    trace.push({attempt,stage:'health',status:health.status,text:String(health.text||'').slice(0,240),latency_ms:Date.now()-started});
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
  return {...last,metadata:{...(last.metadata||{}),bridge:'hive-standard-agent-bridge',bridge_protocol:'async-job-v1',bridge_trace:trace}};
}

function publicJob(job){
  return {
    id:job.id,
    agent_id:job.agent_id,
    state:job.state,
    created_at:job.created_at,
    started_at:job.started_at||null,
    finished_at:job.finished_at||null,
    result:job.state==='done'?job.result:null,
    error:job.state==='failed'?job.error:null
  };
}

function startJob({agentId,task,fresh,timeoutMs}){
  const id=crypto.randomUUID();
  const job={id,agent_id:agentId,state:'queued',created_at:new Date().toISOString(),started_at:null,finished_at:null,result:null,error:null,expires_at:Date.now()+JOB_TTL_MS};
  jobs.set(id,job);
  setImmediate(async()=>{
    job.state='running';
    job.started_at=new Date().toISOString();
    try{
      job.result=await withAgentLock(agentId,()=>invoke(agentId,task,{fresh,timeoutMs}));
      job.state='done';
    }catch(e){
      job.error=String(e?.message||'bridge job failed').slice(0,500);
      job.state='failed';
    }finally{
      job.finished_at=new Date().toISOString();
      job.expires_at=Date.now()+JOB_TTL_MS;
    }
  });
  return job;
}

setInterval(()=>{
  const now=Date.now();
  for(const [id,job] of jobs){
    if((job.state==='done'||job.state==='failed')&&job.expires_at<now)jobs.delete(id);
  }
},60000).unref();

const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url||'/',`http://${req.headers.host||'localhost'}`);
    if(req.method==='GET'&&url.pathname==='/health'){
      return json(res,200,{ok:true,service:'hive-standard-agent-bridge',schema_version:2,protocol:'async-job-v1',agent_count:agentIds.length,jobs:{active:[...jobs.values()].filter(j=>j.state==='queued'||j.state==='running').length}});
    }
    if(!authorized(req))return json(res,401,{ok:false,error:'unauthorized'});
    if(req.method==='GET'&&url.pathname==='/agents'){
      return json(res,200,{ok:true,agents:[...agentIds]});
    }
    if(req.method==='POST'&&url.pathname==='/jobs'){
      const body=await readJson(req);
      const agentId=String(body.agent_id||'').toLowerCase();
      const task=String(body.task||'').trim();
      if(!agentIds.includes(agentId))return json(res,400,{ok:false,error:`UNKNOWN_AGENT:${agentId}`});
      if(!task)return json(res,400,{ok:false,error:'task required'});
      const job=startJob({agentId,task,fresh:body.fresh!==false,timeoutMs:Number(body.timeout_ms)||null});
      return json(res,202,{ok:true,job_id:job.id,state:job.state,protocol:'async-job-v1'});
    }
    if(req.method==='GET'&&url.pathname.startsWith('/jobs/')){
      const id=decodeURIComponent(url.pathname.slice('/jobs/'.length));
      const job=jobs.get(id);
      if(!job)return json(res,404,{ok:false,error:'JOB_NOT_FOUND'});
      return json(res,200,{ok:true,job:publicJob(job)});
    }
    if(req.method==='POST'&&url.pathname==='/invoke'){
      return json(res,426,{ok:false,error:'ASYNC_JOB_PROTOCOL_REQUIRED',submit:'/jobs',poll:'/jobs/{job_id}'});
    }
    return json(res,404,{ok:false,error:'not found'});
  }catch(e){return json(res,e.status||500,{ok:false,error:e.message||'bridge error'});}
});

server.listen(PORT,HOST,()=>{
  console.log(`HIVE_AGENT_BRIDGE_READY=http://${HOST}:${PORT}`);
  console.log('BRIDGE_PROTOCOL=async-job-v1');
  console.log(`AGENTS=${agentIds.join(',')}`);
});

function shutdown(){
  try{closeAll();}catch{}
  server.close(()=>process.exit(0));
  setTimeout(()=>process.exit(0),1500).unref();
}
process.on('SIGINT',shutdown);
process.on('SIGTERM',shutdown);
