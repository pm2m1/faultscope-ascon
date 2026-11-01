import { useEffect, useState } from 'react';
import { BookOpen, ChartNoAxesCombined, ShieldCheck } from 'lucide-react';
import App from './App';
import AlgorithmWalkthrough from './AlgorithmWalkthrough';
import './walkthrough.css';

const isWalkthrough=()=>window.location.hash==='#/walkthrough';
export default function SiteApp(){
  const [walkthrough,setWalkthrough]=useState(isWalkthrough);
  useEffect(()=>{const change=()=>{setWalkthrough(isWalkthrough());window.scrollTo({top:0,behavior:'instant'});};window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change);},[]);
  return <><nav className="site-nav" aria-label="Main pages"><a className="site-nav-brand" href="#/" aria-label="FaultScope home"><ShieldCheck size={20}/><span>FAULTSCOPE <small>ASCON</small></span></a><div><a href="#/" aria-current={!walkthrough?'page':undefined}><ChartNoAxesCombined size={16}/><span>Research Dashboard</span></a><a href="#/walkthrough" aria-current={walkthrough?'page':undefined}><BookOpen size={16}/><span>Algorithm Walkthrough</span></a></div><span className="site-nav-note">RESEARCH + LEARNING</span></nav><div className="site-dashboard" hidden={walkthrough}><App/></div>{walkthrough&&<AlgorithmWalkthrough/>}</>;
}
