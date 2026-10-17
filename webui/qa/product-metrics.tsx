import React from 'react';
import { createRoot } from 'react-dom/client';
import { ProductMetricsConsent } from '../src/components/ProductMetricsConsent';
import type { GatewayClient } from '../src/api';
import '../src/styles.css';
// UI-only fixture. No external account, token or statistics service.
let state = {enabled:false,policy:'product-observation-20261018',pending:0,rejected:0,last_received:null,error:null};
const client = {
 productMetricsStatus:async()=>({...state}),
 configureProductMetrics:async(enabled:boolean,policy:string)=>{state={...state,enabled,policy,pending:enabled?2:0};return {...state};},
 observeProduct:async()=>({queued:true})
} as unknown as GatewayClient;
createRoot(document.getElementById('root')!).render(<React.StrictMode><main style={{maxWidth:850,margin:'24px auto',padding:16}}><ProductMetricsConsent client={client}/></main></React.StrictMode>);
