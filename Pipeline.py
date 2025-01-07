import numpy as np
from QMR.smooth.gaussian_blur import gaussian_blur
import pydicom
import logging
from queue import Queue
import io
import time
import json
import threading
from pathlib import Path
from flask import request, Blueprint, jsonify, make_response,Response, stream_with_context
import os
from middleware import token_required
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from QMR.MPFSL import MPFSL
from ComfyUI.run_pipeline_latest  import DynamicPipeline


pipeline_bp = Blueprint('pipeline', __name__)


class StreamLogHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.queue.put(msg)
        except Exception:
            self.handleError(record)


@pipeline_bp.route('/pipelines/run-once', methods=['POST'])
def run_pipeline():
    try:
        data = request.get_json()
        workflow_json = data.get('workflow')
        workflow = json.loads(workflow_json) if isinstance(workflow_json, str) else workflow_json
        pipeline_id = data.get('id', 1)
        mode = data.get('mode', 'complete')
        nodes = workflow.get('nodes', [])

        for node in nodes:
            if node['id'] == 1:  
                if 'pmt_fields' not in node:
                    node['pmt_fields'] = {}
                if 'outputs' not in node['pmt_fields']:
                    node['pmt_fields']['outputs'] = []
                    
                while len(node['pmt_fields']['outputs']) < 1:
                    node['pmt_fields']['outputs'].append({})
                    
                node['pmt_fields']['outputs'][0].update({
                    'oid': "5635780f-64565673-9b29cf17-d39808a3-29710ad3",
                    'path': "E:\\Code\\PWH_Volunteer_Analysis\\Sample\\MPF\\MPF.dcm",
                    'value': "E:\\Code\\PWH_Volunteer_Analysis\\Sample\\MPF\\MPF.dcm"
                })
                break

        workflow['nodes'] = nodes

        timestamp = time.strftime("%Y%m%d%H%M%S")
        output_path = os.path.join(r"E:\Cloud-Platform\Metaset-Quant Backend", 'ComfyUI', 'test_cache', f'test_pipeline_{timestamp}')
        log_file_path = os.path.join(output_path, "execution_log.log")
        os.makedirs(output_path, exist_ok=True)

        nodes_status = {node['id']: 'pending' for node in nodes}
        log_queue = Queue()
        
        # 设置日志处理
        stream_handler = StreamLogHandler(log_queue)
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [PIPELINE] %(message)s")
        )
        logging.getLogger().addHandler(stream_handler)
        logging.getLogger().setLevel(logging.INFO)

        def run_dyn_pipeline():
            try:
                dyn_pipeline = DynamicPipeline(json.dumps(workflow), output_path)
                dyn_pipeline.execution(mode)
            except Exception as e:
                logging.error(f"Pipeline execution error: {e}")
            finally:
                log_queue.put(None)

        pipeline_thread = threading.Thread(target=run_dyn_pipeline)
        pipeline_thread.daemon = True
        pipeline_thread.start()

        def generate():
            try:
                while True:
                    msg = log_queue.get()
                    if msg is None: 
                        break
                        
                    print("record:", msg)
                    pipeline_finished = "The whole pipeline finished" in msg
                    
                    # response_data = {
                    #     "id": pipeline_id,
                    #     "pythonMsg": {
                    #         "msg": msg
                    #     },
                    #     "graphJson": [
                    #         {
                    #             "id": node['id'],
                    #             "pmtFields": {
                    #                 "status": "done",
                    #                 # "status": nodes_status[node['id']],
                    #                 "outputs": node.get('outputs', [])
                    #             }
                    #         }
                    #         for node in nodes
                    #     ]
                    # }
                    response_data, pipeline_finished = process_pipeline_message(msg, nodes, pipeline_id)
                    yield json.dumps(response_data) + '\n'
                    
                    if pipeline_finished:
                        break

            except Exception as e:
                yield json.dumps({
                    "id": pipeline_id,
                    "pythonMsg": {"msg": f"Error during execution: {str(e)}"},
                    "graphJson": []
                }) + '\n'

            finally:
                logging.getLogger().removeHandler(stream_handler)
                if pipeline_thread.is_alive():
                    pipeline_thread.join(timeout=2.0)


        return Response(
            stream_with_context(generate()),
            mimetype='application/json',
            headers={
                'Transfer-Encoding': 'chunked',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        error_msg = f"Error initializing pipeline: {str(e)}"
        print(error_msg)
        return {"error": error_msg}, 500

@pipeline_bp.route('/pipelines/run-once-test', methods=['POST'])
def run_pipeline1():
    try:
        pipeline_id = 1
        test_path = r"E:\Cloud-Platform\Metaset-Quant Backend\ComfyUI\workflow.json"
        with open(test_path, 'r') as f:
            workflow = json.load(f)

        def generate():
            log_entries = [
                {"node_id": 1, "msg": "Current Level 1, Start Processing Node 1", "status": "running"},
                {"node_id": 1, "msg": "Current node 1 on running", "status": "running"},
                {"node_id": 1, "msg": "Finished Node 1", "status": "done"},
                
                {"node_id": 2, "msg": "Current Level 2, Start Processing Node 2", "status": "running"},
                {"node_id": 2, "msg": "Current node 2 on running", "status": "running"},
                {"node_id": 2, "msg": "Successfully saved data", "status": "done"},
                
                {"node_id": 3, "msg": "Current Level 3, Start Processing Node 3", "status": "running"},
                {"node_id": 3, "msg": "Successfully saved cache data", "status": "done"},
                
                {"node_id": 4, "msg": "Current Level 4, Start Processing Node 4", "status": "running"},
                {"node_id": 4, "msg": "Successfully saved data", "status": "done"}
            ]

            for entry in log_entries:
                node = next((n for n in workflow['nodes'] if n['id'] == entry['node_id']), None)
                if node:
                    chunk = {
                        "id": pipeline_id,
                        "pythonMsg": {
                            "msg": entry['msg']
                        },
                        "graphJson": [{
                            "id": entry['node_id'],
                            "pmtFields": {
                                "status": entry['status'],
                                "outputs": [
                                    {
                                        "name": output.get("name"),
                                        "type": output.get("type"),
                                        "oid": output.get("oid"),
                                        "path": output.get("path"),
                                        "value": output.get("value")
                                    }
                                    for output in node['pmt_fields']['outputs']
                                ]
                            }
                        }]
                    }
                    # 每个chunk以换行符结尾，方便前端解析
                    yield json.dumps(chunk) + '\n'
                    time.sleep(0.5)  # 模拟处理时间

            # 发送完成消息
            yield json.dumps({
                "id": pipeline_id,
                "pythonMsg": {"msg": "Pipeline execution completed"},
                "graphJson": []
            }) + '\n'

        return Response(
            stream_with_context(generate()),
            mimetype='application/json',
            headers={
                'Transfer-Encoding': 'chunked',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        error_msg = f"Error in pipeline execution: {str(e)}"
        print(error_msg)
        return {"error": error_msg}, 500

@pipeline_bp.route('/pipelines/validate', methods=['POST'])
# @token_required()
def validate_pipeline():
    try:
        data = request.get_json()
        workflow = data.get('workflow')
        
        output_path = Path(f'test_cache/validate_{time.strftime("%Y%m%d%H%M%S")}')
        output_path.mkdir(parents=True, exist_ok=True)
        
        dyn_pipeline = DynamicPipeline(workflow, output_path)
        dyn_pipeline.convert_json_to_object()
        results = dyn_pipeline.iterate_node(dyn_pipeline.init_node)
        
        pipelines = results['pipelines']
        final_pipelines = {
            str(i): v for i, (k, v) in enumerate(pipelines.items()) if i > 0
        }
        
        return final_pipelines

    except Exception as e:
        return {"error": str(e)}, 500

@pipeline_bp.route('/pipelines/reset/<int:node_id>', methods=['POST'])
# @token_required()
def reset_node(node_id):
    try:
        data = request.get_json()
        workflow = data.get('workflow')
        
        output_path = Path(f'test_cache/reset_{time.strftime("%Y%m%d%H%M%S")}')
        output_path.mkdir(parents=True, exist_ok=True)
        
        dyn_pipeline = DynamicPipeline(workflow, output_path)
        dyn_pipeline.convert_json_to_object()
        reset_nodes = dyn_pipeline.reset_target_node(node_id)
        
        return {"reset_nodes": reset_nodes}

    except Exception as e:
        return {"error": str(e)}, 500
    



def process_pipeline_message(msg, nodes, pipeline_id):
    try:
        pipeline_msg = msg.split("[PIPELINE]")[1].strip()
    except IndexError:
        return None, False
    
    node_status = {node['id']: node['pmt_fields'].get('status', 'pending') for node in nodes}
    
    if "[STEP" in msg:
        if "Current node" in msg:
            node_id = int(msg.split("node")[1].split()[0])
            node_status[node_id] = 'current'
            for nid in node_status:
                if nid != node_id and node_status[nid] == 'current':
                    node_status[nid] = 'done'
    
    elif "[ERROR]" in msg:
        if "node" in msg:
            try:
                node_id = int(msg.split("node")[1].split()[0])
                node_status[node_id] = 'error'
            except:
                pass
    
    pipeline_finished = "The whole pipeline finished" in msg
    if pipeline_finished:
        for nid in node_status:
            if node_status[nid] != 'error':
                node_status[nid] = 'done'

    response_data = {
        "id": pipeline_id,
        "pythonMsg": {
            "msg": pipeline_msg
        },
        "graphJson": [
            {
                "id": node['id'],
                "pmtFields": {
                    "status": node_status[node['id']],
                    "outputs": node.get('outputs', [])
                }
            }
            for node in nodes
        ]
    }
    
    return response_data, pipeline_finished