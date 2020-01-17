#coding: utf-8

import numpy as np
import pandas as pd
import os, multiprocessing, random
from utils import dir_helper
from utils.read_format_data import read_edgelist_from_dataframe

import networkx as nx
from grakel import GraphKernel


class StructuralNetworkGenerator:
    base_path: str
    input_base_path: str
    output_base_path: str
    node_file: str
    full_node_list: list

    def __init__(self, base_path, node_file, input_folder='1.format', output_folder='dynSPE'):
        self.base_path = base_path
        self.input_base_path = os.path.join(base_path, input_folder)
        self.output_base_path = os.path.join(base_path, output_folder)

        nodes_set = pd.read_csv(os.path.join(base_path, node_file), names=['node'])
        nodes_set = nodes_set['node'].values.tolist()
        self.full_node_list = nodes_set
        self.node_file = node_file

        tem_dir = ['node_subgraph', 'structural_network_adjacent']
        for tem in tem_dir:
            dir_helper.check_and_make_path(os.path.join(self.output_base_path, tem))

    def get_structural_network_all_time(self, worker=-1, max_cnt=100, min_sim=0.5):
        print("getting all timestamps structural network adjacent...")

        f_list = os.listdir(self.input_base_path)
        length = len(f_list)

        if worker <= 0:
            for i, f_name in enumerate(f_list):
                self.get_structural_network(
                    input_file=os.path.join(self.output_base_path, "node_subgraph", f_name),
                    output_file=os.path.join(self.output_base_path, "structural_network_adjacent", f_name),
                    file_num=length, i=i, max_cnt=max_cnt, min_sim=min_sim)

        else:
            worker = min(worker, length, os.cpu_count())
            pool = multiprocessing.Pool(processes=worker)
            print("\tstart " + str(worker) + " worker(s)")

            for i, f_name in enumerate(f_list):
                pool.apply_async(self.get_structural_network, (
                    os.path.join(self.output_base_path, "node_subgraph", f_name),
                    os.path.join(self.output_base_path, "structural_network_adjacent", f_name), length, i, max_cnt, min_sim))

            pool.close()
            pool.join()
        print("got it...")

    def get_structural_network(self, input_file, output_file, file_num, i, max_cnt=100, min_sim=0.5):
        print('\t', str(file_num - i), ' file(s) left')
        if os.path.exists(output_file):
            print('\t', output_file, "exist")
            print('\t', str(file_num - i), ' finished')
            return

        df_subgraph = pd.read_csv(input_file, sep="\t", index_col=0, dtype=str)
        df_subgraph['data'] = df_subgraph['data'].map(lambda row: eval(row))
        df_subgraph['neighbor'] = df_subgraph['neighbor'].apply(np.int)
        node_list = list(df_subgraph.index)
        df_subgraph['node'] = node_list

        neighbor_node_list = df_subgraph.loc[df_subgraph['neighbor'] == 1, 'node'].tolist()
        single_node_list = df_subgraph.loc[df_subgraph['neighbor'] == 0, 'node'].tolist()

        wl_kernel = GraphKernel(kernel=[{"name": "weisfeiler_lehman", "n_iter": 5}, "subtree_wl"], normalize=True)
        df_structural_edges = pd.DataFrame(columns=['from_id', 'to_id', 'weight'])

        def calc_structural_similarity(series, max_cnt=None, min_sim=None):
            global df_structural_edges
            node_id = series['node']
            neighbor_type = series['neighbor']
            cnt = random.randint(1, max_cnt)
            if neighbor_type == 1:
                sampled_nodes = random.sample(neighbor_node_list, cnt)
            else:
                sampled_nodes = random.sample(single_node_list, cnt)
            sampled_subgraph_list = df_subgraph.loc[sampled_nodes, 'data'].tolist()
            df_sim = pd.DataFrame(sampled_nodes, columns=['to_id'])
            wl_kernel.fit(df_subgraph.loc[node_id, 'data'])
            df_sim['weight'] = wl_kernel.transform(sampled_subgraph_list)
            cond = (df_sim['weight'] >= min_sim)
            if cond.sum() == 0:
                return
            df_sim = df_sim.loc[cond, :]
            df_sim['from_id'] = node_id
            df_sim['weight'] = 1

            df_structural_edges = pd.concat([df_structural_edges, df_sim], df_sim)
            return

        df_subgraph.apply(calc_structural_similarity, max_cnt=max_cnt, min_sim=min_sim)
        df_structural_edges.to_csv(output_file, sep='\t', index=True, header=True)
        print('\t', str(file_num - i), ' finished')

    def prepare_subgraph_data_folder(self, layer=1, with_weight=True, worker=-1):
        print("prepare subgraph data...")

        f_list = os.listdir(self.input_base_path)
        length = len(f_list)

        if worker <= 0:
            for i, f_name in enumerate(f_list):
                self.prepare_subgraph_data_file(input_file=os.path.join(self.input_base_path, f_name),
                                                        output_file=os.path.join(self.output_base_path,
                                                                                 "node_subgraph", f_name),
                                                        layer=layer, with_weight=with_weight, file_num=length, i=i)
        else:
            worker = min(worker, length, os.cpu_count())
            pool = multiprocessing.Pool(processes=worker)
            print("\tstart " + str(worker) + " worker(s)")

            for i, f_name in enumerate(f_list):
                pool.apply_async(self.prepare_subgraph_data_file, (
                    os.path.join(self.input_base_path, f_name),
                    os.path.join(self.output_base_path, "node_subgraph", f_name), length, i,
                    layer, with_weight))

            pool.close()
            pool.join()

        print("finish preparing subgraph data...")

    def prepare_subgraph_data_file(self, input_file, output_file, file_num, i, layer=1, ratio=1, with_weight=True):
        print('\t', str(file_num - i), ' file(s) left')
        if os.path.exists(output_file):
            print('\t', output_file, "exist")
            print('\t', str(file_num - i), ' finished')
            return

        graph: nx.Graph = read_edgelist_from_dataframe(input_file, self.full_node_list)

        # prepare subgraph data
        whole_graph_adj_data = pd.DataFrame(index=self.full_node_list, columns=['data', 'neighbor'])
        #whole_graph_adj_data['data'] = [[[[0]], {0: 'N'}]] * len(self.full_node_list)
        #whole_graph_adj_data['neighbor'] = 0

        # 邻接层数
        # layer = 1
        for node in graph.nodes:
            # 边邻接矩阵
            subgraph_nodes = [node]
            need_ergodic = [node]

            neighbor_list = list(graph.neighbors(node))
            neighbor_num = len(neighbor_list)
            neigbor_type = 0 # single point

            if neighbor_num > 0:
                neigbor_type = 1 # not single point
                for i in range(layer):
                    curlayer_neighbor = []
                    for sub_node in need_ergodic:
                        neighbor_list = list(graph.neighbors(sub_node))
                        neighbor_num = len(neighbor_list)
                        if 0 <= ratio < 1:
                            neighbor_list = random.sample(neighbor_list, int(neighbor_num * ratio))
                        curlayer_neighbor += neighbor_list
                    need_ergodic = set(curlayer_neighbor) - set(subgraph_nodes)
                    subgraph_nodes = set(subgraph_nodes + curlayer_neighbor)
            # 有序化
            # 这里测一下graph subgraph在同质点的情况下，矩阵行数不一样会不会得分不一样
            subgraph_nodes = list(subgraph_nodes)
            subgraph_nodes.sort()
            node_adj_matrix = nx.to_pandas_adjacency(graph, subgraph_nodes, dtype=int,
                                                     weight="weight" if with_weight else "without_weight")
            adj_list = np.array(node_adj_matrix).tolist()

            # 节点类型
            # 这里都是同质的，仅考虑结构
            node_type = {}
            num = len(subgraph_nodes)
            for i in range(num):
                node_type[i] = "N"  # Node

            # print([adj_list, node_type])
            whole_graph_adj_data.loc[node] = {'data': [adj_list, node_type], 'neighbor': neigbor_type}
        # print(whole_graph_adj_data)
        whole_graph_adj_data.to_csv(output_file, sep="\t", header=True, index=True)
        # whole_graph_adj_list = np.array(whole_graph_adj_data).tolist()
        print('\t', str(file_num - i), ' finished')


if __name__ == "__main__":

    s = StructuralNetworkGenerator(base_path="..\\data\\enron", input_folder="1.format",
                                   output_folder="dynSPE", node_file="nodes_set\\nodes.csv")
    # s.prepare_subgraph_data_file_optimize_test()
    s.prepare_subgraph_data_folder(worker=10)
    s.get_structural_network_all_time(worker=10)