import numpy as np
from QMR.smooth.gaussian_blur import gaussian_blur
import pydicom
import logging
import requests
from queue import Queue
import io
import re
import time
import json
import threading
from pathlib import Path
from flask import request, Blueprint, jsonify, make_response,Response, stream_with_context
import os
from middleware import token_required
from QMR.MPFSL import MPFSL
from ComfyUI.run_pipeline_latest  import DynamicPipeline


pipeline_bp = Blueprint('pipeline', __name__)
orthanc_url = "http://127.0.0.1:8042"


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


class PipelineHandler:
    def __init__(self):
        self.dyn_pipeline = None
        self.log_queue = Queue()
        self.stream_handler = None
        self.current_node_id = None
        
    def run_dyn_pipeline(self, workflow, output_path, mode):
        try:
            self.dyn_pipeline = DynamicPipeline(json.dumps(workflow), output_path)
            self.dyn_pipeline.execution(mode)
        except Exception as e:
            logging.error(f"Pipeline execution error: {e}")
        finally:
            self.log_queue.put(None)

    def process_pipeline_message(self, msg, nodes, pipeline_id, output_path):
        pipeline_finished = "The whole pipeline finished" in msg
        response_data = {
            "id": pipeline_id,
            "pythonMsg": {"msg": msg},
            "graphJson": []
        }
        
        if "Current node" in msg and "on running" in msg:
            try:
                self.current_node_id = int(msg.split("node")[1].split()[0])
                node_data = {
                    "id": self.current_node_id,
                    "pmtFields": {
                        "status": "running",
                        "outputs": []
                    }
                }
                response_data["graphJson"] = [node_data]
            except Exception as e:
                logging.error(f"Error parsing node id: {e}")
        
        elif "[STEP" in msg and "OFF]" in msg and self.current_node_id is not None:
            try:
                node_dir = f"node_{self.current_node_id}"
                results_path = os.path.join(output_path, node_dir, "results.json")
                
                node_data = {
                    "id": self.current_node_id,
                    "pmtFields": {
                        "status": "done",
                        "outputs": []  
                    }
                }

                if os.path.exists(results_path):
                    try:
                        with open(results_path, 'r') as f:
                            results = json.load(f)
                            outputs = results.get("outputs", [])
                            processed_outputs = process_dicom_output(outputs)
                            node_data["pmtFields"]["outputs"] = processed_outputs
                    except Exception as e:
                        logging.error(f"Error reading results.json for node {self.current_node_id}: {e}")
                
                response_data["graphJson"] = [node_data]
                self.current_node_id = None

            except Exception as e:
                logging.error(f"Error processing step completion: {e}")
        
        elif "[ERROR]" in msg:
            try:
                error_node_match = re.search(r"node (\d+)", msg)
                if error_node_match:
                    node_id = int(error_node_match.group(1))
                    node_data = {
                        "id": node_id,
                        "pmtFields": {
                            "status": "error",
                            "error_message": msg.split("[ERROR]")[1].strip(),
                            "outputs": []
                        }
                    }
                    response_data["graphJson"] = [node_data]
                    self.current_node_id = None  # 发生错误时也清除当前节点ID
            except Exception as e:
                logging.error(f"Error processing error message: {e}")
        
        return response_data, pipeline_finished

    def generate(self, nodes, pipeline_id, pipeline_thread, output_path):
        try:
            while True:
                msg = self.log_queue.get()
                if msg is None:
                    break
                    
                print("record:", msg)
                pipeline_finished = "The whole pipeline finished" in msg
    
                response_data, pipeline_finished = self.process_pipeline_message(msg, nodes, pipeline_id, output_path)
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
            logging.getLogger().removeHandler(self.stream_handler)
            if pipeline_thread.is_alive():
                pipeline_thread.join(timeout=2.0)

@pipeline_bp.route('/pipelines/run-once', methods=['POST'])
def run_pipeline():
    try:
        data = request.get_json()
        workflow_json = data.get('workflow')
        workflow = json.loads(workflow_json) if isinstance(workflow_json, str) else workflow_json
        pipeline_id = data.get('id', 1)
        mode = data.get('mode', 'complete')
        nodes = workflow.get('nodes', [])

        timestamp = time.strftime("%Y%m%d%H%M%S")
        base_path = r"E:\Cloud-Platform\Metaset-Quant Backend\ComfyUI"
        output_path = os.path.join(base_path, 'test_cache', f'test_pipeline_{timestamp}')
        os.makedirs(output_path, exist_ok=True)

        for node in nodes:
            if node['id'] == 1:  
                setup_input_node(node, output_path, orthanc_url)

        workflow['nodes'] = nodes

        handler = PipelineHandler()
        handler.stream_handler = StreamLogHandler(handler.log_queue)
        handler.stream_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [PIPELINE] %(message)s")
        )
        logging.getLogger().addHandler(handler.stream_handler)
        logging.getLogger().setLevel(logging.INFO)

        pipeline_thread = threading.Thread(
            target=handler.run_dyn_pipeline,
            args=(workflow, output_path, mode)
        )
        pipeline_thread.daemon = True
        pipeline_thread.start()

        return Response(
            stream_with_context(handler.generate(nodes, pipeline_id, pipeline_thread, output_path)),
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
    

def setup_input_node(node, output_path, orthanc_url):
    if node['id'] == 1:
        if 'pmt_fields' not in node:
            node['pmt_fields'] = {}
        if 'outputs' not in node['pmt_fields']:
            node['pmt_fields']['outputs'] = []
            
        while len(node['pmt_fields']['outputs']) < 1:
            node['pmt_fields']['outputs'].append({})
            
        instance_id = node.get('widgets_values', [''])[0]
        if not instance_id:
            raise ValueError("No instance ID provided in widgets_values")
            
        try:
            input_dir = os.path.join(output_path, "input")
            os.makedirs(input_dir, exist_ok=True)
            
            instance_url = f"{orthanc_url}/instances/{instance_id}/file"
            file_path = os.path.join(input_dir, f"instance_{instance_id}.dcm")
            
            response = requests.get(instance_url)
            response.raise_for_status()  
            
            with open(file_path, "wb") as file:
                file.write(response.content)
            
            node['pmt_fields']['outputs'][0].update({
                'oid': instance_id,
                'path': file_path,
                'value': file_path
            })
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download file from Orthanc: {str(e)}")
        except IOError as e:
            raise Exception(f"Failed to save file: {str(e)}")


def process_dicom_output(outputs, orthanc_url="http://127.0.0.1:8042"):
    processed_outputs = []
    
    for output in outputs:
        output_copy = output.copy()
        
        if output.get('output_type') == 'DICOM_FILE':
            try:
                dcm = pydicom.dcmread(output['output_path'])
                instance_uid = dcm.SOPInstanceUID
                
                with open(output['output_path'], 'rb') as f:
                    dicom_content = f.read()
                
                headers = {'Content-Type': 'application/dicom'}
                response = requests.post(
                    f"{orthanc_url}/instances", 
                    data=dicom_content,
                    headers=headers
                )
                response.raise_for_status()
                
                orthanc_id = response.json()['ID']
                
                output_copy['oid'] = orthanc_id
                output_copy['instanceUid'] = instance_uid
                
            except Exception as e:
                logging.error(f"Error processing DICOM: {str(e)}")
                output_copy['message'] = f"Error processing DICOM: {str(e)}"
        
        processed_outputs.append(output_copy)

    return processed_outputs


