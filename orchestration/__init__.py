from langgraph.graph import END, StateGraph, START
from langgraph.checkpoint.memory import MemorySaver
from orchestration.node import Node
from orchestration.edges import Edges
from orchestration.states import GraphState

class Graph:
    def __init__(self,state):
        self.state = state
        self.workflow = StateGraph(GraphState)

    def add_workflow_node(self, node_name, node_method):
        self.workflow.add_node(node_name, node_method)

    def add_workflow_edge(self, start_node, end_node):
        self.workflow.add_edge(start_node, end_node)

    def add_extraction_nodes(self):
        self.add_workflow_node("current_thread_extractor", Node.current_thread_extractor)
        self.add_workflow_node("crn_extractor_tool", Node.crn_extractor_tool)
        self.add_workflow_node("all_threads_extraction", Node.all_threads_extraction)
        self.add_workflow_node("db_extractor_tool", Node.db_extractor_tool)

    def add_response_nodes(self):
        self.add_workflow_node("classification_model", Node.classification_model)
        self.add_workflow_node("manual_json_output", Node.manual_json_output)
        self.add_workflow_node("json_output", Node.json_output)
        

    def add_llm_nodes(self):
        self.add_workflow_node("next_action_predictor",Node.next_action_predictor)


    def graph_build(self):
        memory = MemorySaver()
        self.add_extraction_nodes()
        self.add_response_nodes()
        self.add_llm_nodes()
        
        self.add_workflow_edge(START, "current_thread_extractor")
        self.add_workflow_edge("current_thread_extractor", "classification_model")
        self.workflow.add_conditional_edges(
            "classification_model",
            Edges.is_llm_call_required,
            {
                "YES": "crn_extractor_tool", 
                "NO": "manual_json_output",
            },
        )
        self.add_workflow_edge("manual_json_output",END)
        self.add_workflow_edge("crn_extractor_tool", "all_threads_extraction")
        self.add_workflow_edge("crn_extractor_tool", "db_extractor_tool")

        self.add_workflow_edge("all_threads_extraction", "next_action_predictor")
        self.add_workflow_edge("db_extractor_tool", "next_action_predictor")


        self.add_workflow_edge("next_action_predictor", "json_output")
        self.add_workflow_edge("json_output", END)

        result = self.workflow.compile()
        config = {"configurable": {"thread_id": self.state['thread_id']}}
        messsage_state = result.invoke(input = self.state, config=config)
        return messsage_state
