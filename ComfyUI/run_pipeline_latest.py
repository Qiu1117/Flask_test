# Creation Date: Nov 1st 2024
# Author: Jiabo Xu
# Copyright: 2024 Jiabo Xu
# TODOs:
#  1. reverse iteration for efficiently updating node input
#  2. reverse iteration for specific node running
#  3. support more type of input and output 
#  4. argparse for input parameters -- DONE

import time
import json, pickle
import numpy as np
from ComfyUI.filelist2nifti import *
from ComfyUI.utils import *
from importlib import import_module
from collections import deque, Counter
from copy import deepcopy
import argparse
import inspect
from ComfyUI.converter import *
import logging



class NodeInput:
  def __init__(self, node, name, type):
    self.belongs_to_node = node
    self.name = name
    self.type = type
    self.value = None
    #self.in_link = link  # duplicated with link in NodeOutput
    self.path = None  # only used on preview or output node
    self.link_from_node = None  # a input node can only be linked from one output node

  def update_value(self, value):
    self.value = value

  def link_from(self, node_output):
    self.link_from_node = node_output

  def __str__(self):
    return f"NodeInput {self.name}: {self.type}, value {self.value}"


class NodeOutput:
  def __init__(self, node, name, type, links, path):
    self.belongs_to_node = node
    self.name = name
    self.type = type
    self.path = path   # path is for loading cache, by default it is []
    self.value = None  # value is to pass in the workflow
    self.out_links = links if links else None 
    self.out_link_to_inputs = {} # {(<node_id>, <node_input_name>): <NodeInput>}

  def link_to(self, node_id, node_input): 
    self.out_link_to_inputs[(node_id, node_input.name)] = node_input   

  def __str__(self):
    return f"NodeOutput {self.name}: {self.type}, link via {self.out_links} to {self.out_link_to_inputs.keys()}"
  

class Node:
  def __init__(self, node_json, level, status='pending'):
    self.id = node_json['id']
    pmt_fields = node_json['pmt_fields']
    self.type = pmt_fields.get('type', 'init')
    self.plugin_name = pmt_fields.get('plugin_name', None)
    self.function_name = pmt_fields.get('function_name', None)
    self.status = pmt_fields.get('status', None)
    self.inputs = {}
    for input in node_json['inputs']:
      self.inputs[input['name']] = NodeInput(self, input['name'], input['type'])
    self.outputs = {}
    # if node_json key output, then it is a function node
    if "outputs" not in node_json:
      self.outputs = None
    else:
      for i, output in enumerate(node_json['outputs']):
        self.outputs[output['name']] = NodeOutput(self, output['name'], output['type'], output['links'], pmt_fields['outputs'][i]['path'])
        if self.type == 'input':
          #self.outputs[output['name']].path = pmt_fields['outputs'][i]['path'] 
          self.outputs[output['name']].value = pmt_fields['outputs'][i]['value'] 

    self.properties = pmt_fields.get('args', None)

    self.link_to_nodes = {}  # {<node_id>: <Node>}
    self.link_from_nodes = {} # {<node_id>: <Node>}

    self.level = level
    self.status = status
    self.origin = set()

  def add_origin(self, origin):
    self.origin = self.origin.union(origin)

  def link_from(self, node):
    self.link_from_nodes[node.id] = node

  def link_to(self, node):
    self.link_to_nodes[node.id] = node

  def __eq__(self, other):
    return self.id == other.id 

  def __str__(self):
    text_output = f"Node {self.id}: {self.type}, link to Node {[x for x in self.link_to_nodes.keys()]}"
    return text_output


class DynamicPipeline:
  def __init__(self, pipeline_json, output_info_path='.'):
    pipeline_json = json.loads(pipeline_json)
    self.num_of_nodes = pipeline_json['last_node_id']
    self.node_json = self.preprocess_node_json(pipeline_json['nodes'])
    self.link_json = self.preprocess_link_json(pipeline_json['links'])

    self.output_info_path = output_info_path
    self.init_node = Node({"id":-1, "inputs":[], "outputs":[], "pmt_fields":{'type': 'init'}}, 0, status='pending')
    self.exist_node_dict = {}
    self.output_nodes = {}
    self.current_node = self.init_node

    self.input_nodes = self.get_input_nodes()
    self.end_nodes = {}

    self.exist_node_level_key = {}  # {<level>: [<Node>, ...]}
    
    self.max_level = None
    self.processed_nodes = {}  # {<level>: [<Node>, ...]}
    
    self.ongoing_node_level_key = {}
    self.ongoing_num_of_nodes = 0

    self.current_level = 1


  def preprocess_node_json(self, node_json):
    '''
      convert the node json from list to dictionary whose key is the node id 
    '''
    node_dict = {}
    for node in node_json:
      node_dict[node['id']] = node
    return node_dict
  

  def preprocess_link_json(self, link_json):
    '''
      convert the link json from list to dictionary whose key is the link id 
    '''
    link_dict = {}
    for link in link_json:
      link_dict[link[0]] = link
    return link_dict
  

  def get_input_nodes(self):
    input_nodes = {}
    for node_id, node in self.node_json.items():
      pmt_field = node['pmt_fields']
      status = pmt_field.get('status', None)

      # if status == 'current':
      #   self.current_node = node_obj
      if pmt_field['type'] == 'input':
        node_obj = Node(node, 1, status)
        node_obj.add_origin({node_id})
        self.init_node.link_to(node_obj)
        node_obj.link_from(self.init_node)
        input_nodes[node_obj.id] = node_obj  
        self.exist_node_dict[node_obj.id] = node_obj  # only record input_nodes up to now
      
    return input_nodes


  def _convert_node_dict_to_level_key(self):
    for node_id, node in self.exist_node_dict.items():
      if self.exist_node_level_key.get(node.level):
        self.exist_node_level_key[node.level].append(node)
      else:
        self.exist_node_level_key[node.level] = [node]


  def process_function_node(self, node):
    '''
      1. call function with inputs
      2. assign results to current node's outputs
    '''
    logging.info(f"Processing function node {node.id} {node.plugin_name}.{node.function_name}")
    output_dict = self.run_single_plugin(node)
    self.assign_outputs(node, output_dict)
  

  def process_file2data_converter(self, node):
    logging.info(f"[CONVERTER] Processing converter node {node.id} converter.{node.function_name}")
    try:
      data = run_file2data_converter(node, **node.properties)
      logging.info(f"[CONVERTER] Successfully saved data")
      
      single_output_node_key = next(iter(node.outputs))
      node.outputs[single_output_node_key].value = data  
      logging.info(f"[CONVERTER] Assigned value to Node {node.id}'s output data")
    except Exception as e:
      logging.error(f"[CONVERTER] {e}")   


  def process_data2file_converter(self, node):
    logging.info(f"[CONVERTER] Processing converter node {node.id} converter.{node.function_name}")

    node_folder_path = Path(self.output_info_path) / f"node_{node.id}"
    # create folder for node if not exist
    if not node_folder_path.exists():
      node_folder_path.mkdir(parents=True)
    filepath = node_folder_path / "file"
    try:
      filepath = run_data2file_converter(node, str(filepath), **node.properties)
      logging.info(f"[CONVERTER] Successfully saved data")
      
      single_output_node_key = next(iter(node.outputs))
      #single_output_node.path = filepath   
      node.outputs[single_output_node_key].value = filepath  
      logging.info(f"[CONVERTER] Assigned value to Node {node.id}'s output file")
    except Exception as e:
      logging.error(f"[CONVERTER] {e}")


  def _prepare_func_input(self, node):
    input_dict = {}
    for input_name, input in node.inputs.items():
      input_dict[input_name] = input.value
    input_dict.update(node.properties)
    return input_dict
  
  
  def run_single_plugin(self, node):
    '''
      return a dictionary of output values whose key are their output names
    '''
    logging.info(f"[PLUGIN] Try to run function {node.plugin_name}.{node.function_name}")
    
    import_object = import_module('.'.join(['ComfyUI.scripts', node.plugin_name]))  # type is also the function name
    function = getattr(import_object, node.function_name)
    input_dict = self._prepare_func_input(node)

    verbose_dict = {k: (v.shape, v.min(), v.max()) if isinstance(v, np.ndarray) else v for k, v in input_dict.items()}
    logging.info(f"[PLUGIN] Start to run the function with inputs {verbose_dict} and outputs {node.outputs.keys()}")
    logging.info("[PLUGIN] [LISTEN ON] plugin's print")
    try:
      outputs = function(**input_dict)
      logging.info("[PLUGIN] [LISTEN OFF] plugin execution done")
    except Exception as e:
      logging.error("[PLUGIN] Plugin execution failed, error message: ", str(e))

    if not isinstance(outputs, tuple):
      outputs = (outputs,)

    results = {}
    for i, data in enumerate(list(outputs)):
      output_name = self.node_json[node.id]['outputs'][i]['name'] 
      results[output_name] = data
    return results
  

  def assign_outputs(self, node, output_dict):
    for name, value in output_dict.items():
      node.outputs[name].value = value
      logging.info(f"[ASSIGN_OUTPUTS] Assigned value to Node {node.id}'s output {name}")


  def assign_exist_values_to_inputs_of_toNode(self, from_node):
    for output_name, output in from_node.outputs.items():
      for input_name, to_node_input in output.out_link_to_inputs.items():
        to_node_input.update_value(output.value)
        logging.info(f"[ASSIGN_VALUES_TO_INPUT] Assigned value to Node {to_node_input.belongs_to_node}'s input {to_node_input.name} from Node {from_node.id}'s output {output_name}")

  # def assign_debug_data(self, data_type):
  #   if data_type == '2D':
  #     logging.debug(f"Obtained 2D dummy array")
  #     return ["./sample data/brain_seed002/IMG-0003-00147.dcm"]
  #   elif data_type == 'nifti':
  #     logging.debug(f"Obtained sample NIFTI ")
  #     return ["./sample data/brain_seed002.nii.gz"]
  #   elif data_type == '3D':
  #     logging.debug(f"Obtained sample 3D array from DICOM folder")
  #     return ["./sample data/brain_seed002"]
  #   else:
  #     return None
    
  def get_data_from_path(self, input_path, data_type):
    '''
      get file data from path
    '''
    if data_type in ['2D', '3D', 'nifti']:
      results = dicom_to_2d(input_path) 
      logging.info(f"Retrieved {data_type} data from pickle")
    elif 'FILE' in data_type:
      results = input_path
      logging.info(f"Retrieved {data_type} data from path")
    elif data_type in ['json']:
      results = json.load(open(input_path, 'r'))
      logging.info(f"Retrieved {data_type} data from json")
    else:
      return None
    return results


  def update_node_input_based_on_status_reversely(self, start_from="current"):
    '''
      alwary start from the current node and reversely iterate the graph from the node inputs 
      until all inputs of the node are assigned with values, record all nodes need to be processed and already processed

      start_from: 
        "current": start from the current node (used for efficient running once) 
        "output": start from the output nodes (used for efficient batch processing)
        "all": start from all end nodes (used for efficient completing)
    '''
    print('-----------------------------------')
    logging.info('Start prepare node input based on status reversely from current node')
    # prapare start node
    if start_from == "current" and self.current_node != self.init_node:
      self.ongoing_node_level_key[self.current_node.level].append(self.current_node)
      self.ongoing_num_of_nodes += 1
      pending_nodes = deque([self.current_node])
    elif start_from == "output":
      pending_nodes = deque()
      for _, output_node in self.output_nodes.items():
        self.ongoing_node_level_key[output_node.level].append(output_node)
        self.ongoing_num_of_nodes += 1
        pending_nodes.append(output_node)
    elif start_from == "all":
      pending_nodes = deque()
      for node_id, node in self.end_nodes.items():
        self.ongoing_node_level_key[node.level].append(node)
        self.ongoing_num_of_nodes += 1
        pending_nodes.append(node)
    else:
      raise ValueError(f"Invalid start_from parameter {start_from}")
    
    while len(pending_nodes) > 0:
      node = pending_nodes.popleft()

      for input_name, input_node in node.inputs.items():
        if input_node.link_from_node:
          output_node = input_node.link_from_node
          from_node = output_node.belongs_to_node

          if from_node.status == 'done':  
            if output_node.value:
              pass
            if from_node not in self.processed_nodes[from_node.level]:
              self.processed_nodes[from_node.level].append(from_node)
          else:  # not yet have value, keep iterating
            if from_node not in self.ongoing_node_level_key[from_node.level]:
              self.ongoing_node_level_key[from_node.level].append(from_node)
              self.ongoing_num_of_nodes += 1
              pending_nodes.append(from_node)

    logging.info('Finished updating node input based on status')
    print('-----------------------------------')
    logging.debug(f"processed_nodes: {self.processed_nodes}")
    d = {}
    for level,v in self.ongoing_node_level_key.items():
      d[level]= [node.id for node in v] 
    logging.debug(f"ongoing_node_level_key: {d}")
    print('-----------------------------------')


  def update_node_based_on_status(self):  # not efficient enough
    print('-----------------------------------')
    logging.info('Started updating node input based on status')
    logging.debug(f"exist_node_level_key: ", self.exist_node_level_key)
    for i in range(1, self.max_level+1):
      for node in self.exist_node_level_key[i]:
        if node.status == 'done' or node.type == 'input':
          if node.type == 'output':
            continue
          elif node.type == 'input':
            node.status = 'done'
          self.processed_nodes[i].append(node)
        else:
          self.ongoing_node_level_key[i].append(node)
          self.ongoing_num_of_nodes += 1

    logging.info('Finish updating node input based on status')
    print('-----------------------------------')
    logging.debug(f"ongoing_node_level_key: ", self.ongoing_node_level_key)
    print('-----------------------------------')


  def process_done_node(self):
    for i in range(1, self.max_level+1):
      for node in self.processed_nodes[i]:
        for output_name, output in node.outputs.items():
          output.value = self.get_data_from_path(output.path, output.type)  # obtain value from cache
          logging.info(f"Assign value to Node {node.id}'s input {output_name} value type is {type(output.value)}")

        self.assign_exist_values_to_inputs_of_toNode(node)


  def convert_json_to_object(self):
    pending_nodes = deque()
    for k, node in self.input_nodes.items():
      pending_nodes.append(node)

    while(len(pending_nodes) > 0):
      from_node = pending_nodes.popleft()
      current_level = from_node.level
      new_level = current_level+1

      deque_list = list(pending_nodes)
      logging.info(f"Current Level {current_level}, Start Processing Node {from_node.id}")
      logging.info(f"Pending Nodes {[node.id for node in deque_list]}")
      if from_node.outputs:
        has_outlink = False
        for name, output in from_node.outputs.items():
          logging.info(f"Start processing Output {output.out_links}")
          if output.out_links:
            has_outlink = True
            for link in output.out_links:
              logging.info(f"Processing Link {link}")
              target_link_json = self.link_json[link]
              link_to_node_id = target_link_json[3] 
              link_to_node_input_idx = target_link_json[4] 

              to_node_info = self.node_json[link_to_node_id] 
              to_node_id = to_node_info['id']

              if from_node.link_to_nodes.get(to_node_id):  # link between from_node and to_node already exists
                logging.info(f"Link from {from_node.id} to {to_node.id} already exists")
              elif self.exist_node_dict.get(to_node_id):   # link between current tree and to_node already exists
                existed_link_to_node = self.exist_node_dict[to_node_id]
                to_node = existed_link_to_node
                if new_level <= existed_link_to_node.level:
                  new_level = existed_link_to_node.level
                  logging.info(f"Keep level of {existed_link_to_node.id} new level on {existed_link_to_node.level}")
                else:
                  logging.info(f"Update level of {existed_link_to_node.id} new level on {existed_link_to_node.level}")
                existed_link_to_node.level = new_level
                
                from_node.link_to(to_node)
                to_node.link_from(from_node)

                logging.info(f"Linking from {from_node.id} To {to_node.id} level on {new_level}")
              else:
                status = to_node_info['pmt_fields']['status']
                to_node = Node(to_node_info, new_level, status)  
                to_node.add_origin(from_node.origin)
                self.exist_node_dict[to_node_id] = to_node
                if status == 'current':
                  self.current_node = to_node
                if to_node.type == 'output':
                  self.output_nodes[to_node_id] = to_node
                pending_nodes.append(to_node)
                logging.info(f"Pushed Node {to_node.id} status: {status}")
              
                from_node.link_to(to_node)
                to_node.link_from(from_node)

                logging.info(f"Linked from {from_node.id} To {to_node.id} level on {new_level}")
              
              # link output node of from_node to input node of to_node
              to_node_input_name = to_node_info['inputs'][link_to_node_input_idx]['name']
              input_node_of_to_node = to_node.inputs[to_node_input_name]

              output.link_to(to_node_id, input_node_of_to_node)
              input_node_of_to_node.link_from(output)

              logging.info(f"Linked {output.out_link_to_inputs[(to_node_id, to_node_input_name)]} to {input_node_of_to_node.name} of Node {to_node.id}")
              
          else:
            logging.info(f"No links for output {name} of Node {from_node.id}")
        if not has_outlink:
            self.end_nodes[from_node.id] = from_node
            logging.info(f"Add End node {from_node.id}")
      else:
        self.end_nodes[from_node.id] = from_node
        logging.info(f"Add End node {from_node.id}")
      logging.info(f"Finished Node {from_node.id}")
      print(f'-----------------------------------')
  

  def step(self, steps=1):
    '''
      execute the pipeline steps forward, save the output of each step
      steps = -1 for running all nodes
    '''
    num = 1
    for i in range(1, self.max_level+1):
      print(f'---------------------------------------------')
      logging.info(f"Current Level {i}")

      while self.ongoing_node_level_key[i]:
        node = self.ongoing_node_level_key[i][0]

        logging.info(f"[STEP {num} ON]")
        logging.info(f"Current node {node.id} on running")

        if node.type == 'input':  # input nodes are processed in self.process_done_node
          pass
        elif node.type == 'manual':
          logging.info(f"[MANUAL] Manual node {node.id} is waiting for user inputs")
          self.sustain_manual(node)
        elif node.plugin_name == 'data_to_file':
          self.process_data2file_converter(node)
          self.sustain(node)
        elif node.plugin_name in ['file_to_data', 'data_to_data']:
          self.process_file2data_converter(node)
          self.sustain(node)
        elif node.type == 'preview' or node.type == 'output':
          # preview only for UI usage
          # output only for batch processing usage
          pass
        else:
          self.process_function_node(node)
          self.sustain(node)

        self.assign_exist_values_to_inputs_of_toNode(node)
        node.status = 'done'

        self.ongoing_node_level_key[i].remove(node)
        self.processed_nodes[i].append(node)

        #self.current_node = node
        graph_json = self.convert_graph_to_json()
        with open(Path(self.output_info_path) / f'graph_{num}.json', 'w') as f:
          json.dump(graph_json, f)  
        logging.info(f"[STEP {num} OFF]")

        num += 1
        steps -= 1
        if steps == 0:
          if self.ongoing_node_level_key[i]:
            self.ongoing_node_level_key[i][0].status = 'current'
          elif self.ongoing_node_level_key[i] == [] and i+1 <= self.max_level:
            self.exist_node_level_key[i+1][0].status = 'current'
          break

      if steps == 0:
        if i+1 <= self.max_level:
          self.exist_node_level_key[i+1][0].status = 'current'  # update status of the entire graph
        elif i == self.max_level:
          graph_json = self.convert_graph_to_json()
          with open(Path(self.output_info_path) / f'graph_final.json', 'w') as f:
            json.dump(graph_json, f)  
          logging.info(f"The whole pipeline finished")
        break


  def run_for_batch(self):
    '''
      Run the pipeline for batch processing by ignoring all intermediate outputs.
      Also, the pipeline processing cannot be interrupted in the middle.  
    '''
    # for k,v in self.exist_node_dict.items():
    #   print(k)
    #   for kk, vv in v.inputs.items():
    #     print(kk, vv.link_from_node)

    for i in range(1, self.max_level+1):
      print('------------------------------------')
      logging.info(f"Current Level {i}")
      while self.ongoing_node_level_key[i]:
        node = self.ongoing_node_level_key[i][0]
        logging.info(f"Current node {node.id} on running")
        
        if node.type == 'input':  # the logic of input node is same as function node
          pass
        elif node.type == 'preview':  
          pass
        elif node.type == 'manual':
          logging.info(f"[MANUAL] Manual node {node.id} is waiting for user inputs")
          self.sustain_manual(node)
        elif node.plugin_name == 'data_to_file':
          self.process_data2file_converter(node)
        elif node.plugin_name in ['file_to_data', 'data_to_data']:
          self.process_file2data_converter(node)
        elif node.type == 'output':
          for input_name, input_node in node.inputs.items():
            output_node = input_node.link_from_node
            if output_node:  # deal with optional inputs
              self.sustain_output(output_node)
        else:
          self.process_function_node(node)
          self.assign_exist_values_to_inputs_of_toNode(node)

        self.ongoing_node_level_key[i].remove(node)

    graph_json = self.convert_graph_to_json()
    with open(Path(self.output_info_path) / f'graph.json', 'w') as f:
        json.dump(graph_json, f) 


  def convert_graph_to_json(self):
    '''
      convert current node graph to json for sustaining and front-end display
    '''
    current_node_json = []
    flatten_nodes = [node for k,node in self.exist_node_dict.items()]
    flatten_nodes = sorted(flatten_nodes, key=lambda x: x.id)
    ## convert node to json
    for node in flatten_nodes:
      pmt_fields = {"type": node.type, 
                    "status": node.status}
      
      if node.type == 'input':
        pmt_fields["outputs"] = [{"name": output_name, "type": output_node.type, "path": output_node.path} for output_name, output_node in node.outputs.items()]
      elif node.type == 'preview' or node.type == 'output':
        pmt_fields["outputs"] = [{"name": input_name, "type": input_node.type, "path": input_node.path} for input_name, input_node in node.inputs.items()]
      else:
        pmt_fields["outputs"] = [{"name": output_name, "type": output_node.type, "path": output_node.path} for output_name, output_node in node.outputs.items()]
      
      node_json = {"id": node.id, 
                  "pmt_fields": pmt_fields,
                }
      current_node_json.append(node_json)
    return current_node_json


  def iterate_node(self, node):
    '''
      iterate full node graph start from given node for debugging purpose      
      Note: this code is not for executing the pipeline
    '''
    node_amount = 0 if node.id != self.init_node.id else -1
    node_type_counter = []
    current_deque = deque([node])

    pipelines = {}
    exist_node_id = []
    while(len(current_deque) > 0):
      current_node = current_deque.popleft()

      if current_node.id in exist_node_id:
        continue
      exist_node_id.append(current_node.id)
      node_amount += 1
      
      if tuple(current_node.origin) in pipelines.keys():
        pipelines[tuple(current_node.origin)]["nodes"].append(current_node.id)
      else:
        pipelines[tuple(current_node.origin)] = {"nodes": [current_node.id], "has_output": False}
      
      if current_node.type == 'output':
        pipelines[tuple(current_node.origin)]["has_output"] = True

      node_type_counter.append(current_node.type)

      for node_id, nod in current_node.link_to_nodes.items():
        current_deque.append(nod)
      #print([x.type for x in list(current_deque)])
    result = {'node_amount': node_amount, 
              'types': Counter(node_type_counter),
              'pipelines': pipelines}
    return result


  def sustain_output(self, output_node):
    '''
      only sustain the given output node
    '''
    node = output_node.belongs_to_node
    print('-----------------------------------')
    logging.info(f"Sustaining outputs")

    info = {"plugin_name": node.plugin_name,
          "function_name": node.function_name, 
          "timestemp": time.strftime("%Y%m%d-%H%M%S"),
          "origin_node_ids": list(node.origin),
          "outputs": []} # {"output_name": '',"output_type": '', "upload_oid": '', "message": ''}
    node_folder_path = Path(self.output_info_path) / f"node_{node.id}"
    # create folder for node if not exist
    if not node_folder_path.exists():
      node_folder_path.mkdir(parents=True)
    
    message = 'ok'
    name = output_node.name
    if output_node.path:
      filepath = output_node.path
    else:
      value = output_node.value
      filepath, message = self.export(output_node.type, name, value, node_folder_path)
      output_node.path = str(filepath)

    info['outputs'].append({"output_name": name, 
                            "output_type": output_node.type, 
                            "output_path": str(filepath), 
                            "message": message})
    
    with open(node_folder_path / 'results.json', 'w') as f:
      json.dump(info, f)


  def sustain(self, node):
    '''
      sustain all outputs of the given node
    '''
    print('-----------------------------------')
    logging.info(f"[SUSTAIN] Sustaining outputs")

    info = {"plugin_name": node.plugin_name,
          "function_name": node.function_name, 
          "timestemp": time.strftime("%Y%m%d-%H%M%S"),
          "origin_node_ids": list(node.origin),
          "outputs": []} # {"output_name": '',"output_type": '', "upload_oid": '', "message": ''}
    node_folder_path = Path(self.output_info_path) / f"node_{node.id}"
    # create folder for node if not exist
    if not node_folder_path.exists():
      node_folder_path.mkdir(parents=True)

    message = "ok"
    for name, output_node in node.outputs.items():
      if output_node.path:
        filepath = output_node.path
      else:
        value = output_node.value
        filepath, message = self.export(output_node.type, name, value, node_folder_path)
        output_node.path = str(filepath)
      info['outputs'].append({"output_name": name, 
                              "output_type": output_node.type, 
                              "output_path": str(filepath), 
                              "message": message})
    logging.info(f"[SUSTAIN] Sustaining finished")
    with open(node_folder_path / 'results.json', 'w') as f:
      json.dump(info, f)
      

  def sustain_manual(self, node):
    '''
      sustain the input of manual node
    '''
    print('-----------------------------------')
    logging.info(f"[SUSTAIN] Sustaining  manual node")

    info = {"plugin_name": node.plugin_name,
          "function_name": node.function_name, 
          "timestemp": time.strftime("%Y%m%d-%H%M%S"),
          "origin_node_ids": list(node.origin),
          "inputs": []} # {"output_name": '',"output_type": '', "upload_oid": '', "message": ''}
    node_folder_path = Path(self.output_info_path) / f"node_{node.id}_manual"
    # create folder for node if not exist
    if not node_folder_path.exists():
      node_folder_path.mkdir(parents=True)

    message = "ok"
    for name, input_node in node.inputs.items():
      if input_node.path:
        filepath = input_node.path
      else:
        value = input_node.value
        filepath, message = self.export(input_node.type, name, value, node_folder_path)
        input_node.path = str(filepath)

      info['inputs'].append({"input_name": name, 
                              "input_type": input_node.type, 
                              "input_path": str(filepath), 
                              "message": message})
    
    with open(node_folder_path / 'results.json', 'w') as f:
      json.dump(info, f)
    logging.info(f"[SUSTAIN] Sustaining finished")
    

  def export(self, output_node_type, name, value, node_folder_path):
    file_path = None
    message = "ok"
    if output_node_type in ['2D', '3D']:
      file_path = node_folder_path / name
      try:
        with open(file_path, 'wb') as f:
          pickle.dump(value, f)
        logging.info(f"Successfully saved cache data into pickle {name}")
      except Exception as e:
        message = f"Error in saving pickle data {name}, {e}"
        logging.error(message)
    elif 'FILE' in output_node_type:  # means the input(value) is already a string of path
      file_path = value
    elif output_node_type in ['json']:
      file_path = node_folder_path / f"{name}.json"
      with open(file_path, 'w') as f:
        try:
          json.dump(value, f)
          logging.info(f"Successfully create json file {name}")
        except Exception as e:
          message = f"Error in writing json file {name}, {e}"
          logging.error(message)
    else:
      pass
    return file_path, message


  def reset_target_node(self, node_id) -> list[int]:
    '''
      reset the target node and its downstream nodes
    '''
    ## search node based on node id
    node = None
    for k, v in self.exist_node_dict.items():
      if v.id == node_id:
        node = v
        break
    reset_node_ids = []
    current_deque = deque([node])
    while len(current_deque) > 0:
      current_node = current_deque.popleft()
      reset_node_ids.append(current_node.id)
      for node_id, nod in current_node.link_to_nodes.items():
        current_deque.append(nod)
    return reset_node_ids
  

  def execution(self, mode):
    '''
      mode = {"one-step", "complete", "to-node", "batch"}
        one-step: run one more node in order
        complete: run all node of the pipeline graph
        to-node: run until the specific node
        batch: run all node when batch-processing, not record intermediate results
    '''
    with open(Path(self.output_info_path) / "execution_log.log", 'w') as f:
      pass
    logging.basicConfig(
      level=logging.DEBUG,
      format="%(asctime)s [%(levelname)s] [PIPELINE] %(message)s",
      handlers=[
          logging.FileHandler(Path(self.output_info_path) / "execution_log.log"),
          logging.StreamHandler()
      ]
    )

    ### Prepare node_graph object
    self.convert_json_to_object()
    self._convert_node_dict_to_level_key()

    self.max_level = max(self.exist_node_level_key.keys())
    logging.info(f"Max level of the pipeline is {self.max_level}")
    ### Update node status 
    for i in range(1, self.max_level+1):
      self.processed_nodes[i] = []
    for i in range(1, self.max_level+1):
      self.ongoing_node_level_key[i] = []
    
    ### Mount value to input nodes of all of the pending nodes

    if mode == 'batch':
#      self.update_node_based_on_status()
      self.update_node_input_based_on_status_reversely(start_from="output")
      self.process_done_node()
      self.run_for_batch()
    elif mode == 'complete':
      self.update_node_input_based_on_status_reversely(start_from="all")
      self.process_done_node()
      self.step(self.ongoing_num_of_nodes)
    elif mode == 'one-step':
      self.update_node_input_based_on_status_reversely(start_from="all")
      self.process_done_node()
      self.step(steps=1)
    elif mode == 'to-node':
      self.update_node_input_based_on_status_reversely(start_from="current")
      self.process_done_node()
      self.step(self.ongoing_num_of_nodes)


if __name__ == '__main__':

  parser = argparse.ArgumentParser(
        prog='DynamicPipeline', 
        description='Process the pipeline with dynamically with any given nodes', 
        epilog='Copyright(r), 2024 Jiabo Xu'
    )

  parser.add_argument('-p', '--pipeline', default='test_pipeline/workflow.json',
                      type=str, help="the path of the pipeline.json file")
  parser.add_argument('-m', '--mode', default="complete", type=str, help='''
                      Pick either:
                        batch - run-batch
                        complete - run all nodes of the pipeline graph
                        one-step - run one node forward in order
                        to-node - run to the specific node
                      ''')
  parser.add_argument('-o', '--output', default=f'test_cache/test_pipeline_{time.strftime("%Y%m%d%H%M%S")}', 
                                        type=str, help="store cache info and results")
  parser.add_argument('-r', '--reset', type=int, help="call function to get reset node ids with given node id and pipeline json") 
  parser.add_argument('-v', '--validate', action='store_true', help="call function to validate the pipeline graph return a dict of graph info in terms of validation info") 
  
  args = parser.parse_args()

  # create folder for node if not exist
  output_info_path=Path(args.output)
  if not output_info_path.exists():
    output_info_path.mkdir(parents=True)

  with open(args.pipeline, 'r') as f:
      pipeline_json = json.load(f)

  dyn_pipeline = DynamicPipeline(json.dumps(pipeline_json), output_info_path)
  if args.reset:
    dyn_pipeline.convert_json_to_object()
    print(dyn_pipeline.reset_target_node(args.reset))
  elif args.validate:
    dyn_pipeline.convert_json_to_object()
    results = dyn_pipeline.iterate_node(dyn_pipeline.init_node)
    pipelines = results['pipelines']
    final_pipelines = {}
    for i, (k, v) in enumerate(pipelines.items()):
      if i > 0:
        final_pipelines[i] = v
    print(json.dumps(final_pipelines))
  else:
    dyn_pipeline.execution(args.mode)
  
    
  