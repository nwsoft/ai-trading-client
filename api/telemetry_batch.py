"""Bounded 60-second success telemetry batches; order/risk events bypass."""
import json
import threading
import time
import uuid


class TelemetryBatcher:
    def __init__(self):
        self.lock=threading.Lock();self.items={}

    def add(self,item):
        payload=item['payload']
        if payload.get('metadata',{}).get('_already_batched'):
            return False
        if payload['event_type'] not in {'learning_data_recorded','ai_inference_completed'} or payload['status']!='success' or not item.get('headers'):
            return False
        metadata={k:v for k,v in payload['metadata'].items() if k in {'exchange','symbol','execution_mode','mode','model','schema_version'}}
        # Success counters describe the venue/window, not individual signals.
        if 'symbol' in metadata:metadata['symbol']='__aggregate__'
        metadata['_window_start']=int(time.time()//60)*60
        clean={**payload,'metadata':metadata}
        identity={**clean,'metric_value':payload['metric_value'] is not None,'headers':item['headers'],
                  'url':item['url'],'minute':int(time.time()//60)}
        key=json.dumps(identity,sort_keys=True)
        with self.lock:
            if key not in self.items:
                if len(self.items)>=512:return False
                self.items[key]={'item':{**item,'payload':clean},'count':0,'sum':0.,'created':time.monotonic()}
            row=self.items[key]
            if row['count']>=10000:return False
            row['count']+=1;row['sum']+=float(payload['metric_value'] or 0.)
        return True

    def ready(self,force=False):
        with self.lock:
            rows=[self.items.pop(key) for key,row in list(self.items.items()) if force or time.monotonic()-row['created']>=60]
        result=[]
        for row in rows:
            item=row['item'];payload=item['payload']
            if payload['metric_value'] is not None:payload['metric_value']=row['sum']/row['count']
            payload['metadata'].update(_count=row['count'],_batch_id=uuid.uuid4().hex,_already_batched=True)
            item['max_attempts']=3
            result.append(item)
        return result
