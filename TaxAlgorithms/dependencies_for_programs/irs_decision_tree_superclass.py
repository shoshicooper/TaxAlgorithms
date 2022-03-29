"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Important note: This is NOT named after the computer science term 'decision tree', which is a technical term and refers
to something else.  This is named after the IRS term 'decision tree', which they often use in literature to describe
whether or not someone is permitted to use a certain filing status or take a certain deduction/credit.

This superclass should allow you to build a tree for various different IRS situations that may arise.  Upon traversal,
you will eventually wind up at the ending node -- which is the node that states what tax treatment applies.  You can
then retrieve that ending node and get information about applicable tax treatment.
"""


class IrsDecisionNode(object):
    """
    A node in the tree.
    The right child will be used when if_func is true. Left child will be used when if_func is false.
    """

    def __init__(self, description, identifier, side, if_func=None,
                 traversal_func=lambda itself, **kwargs: itself.side):
        """
        Initializes the Node
        :param description: string description of the node.  If one were to use this tree as a questionnaire for the
            actual taxpayer, this would be what you would ask the taxpayer to see which branch to take.
        :param identifier: a way to easily identify the node.
        :param if_func: A function that takes parameter: **kwargs
                It must return a boolean (True/False) which will determine which path we use in the tree.
                The **kwargs it takes is the traversal dictionary, which will remain constant throughout the traversal.
                kwargs["traversal_value"] can be used to represent the value passed down during traversal.
        :param side: if it's a left child or a right child, as represented by 0 (left child) or 1 (right child)
        :param traversal_func: if you want to do something during traversal, then that function will go here.
                            Again, remember the **kwargs.
        """
        self.identifier = identifier
        self.description = description
        self.side = side
        self.func = if_func
        self.traversal_func = traversal_func

        self.storage = []

        self.left_child = None
        self.right_child = None


    def set_true(self, node):
        self.right_child = node

    def set_false(self, node):
        self.left_child = node

    @property
    def true(self):
        return self.right_child

    @property
    def false(self):
        return self.left_child


    def traverse(self, values:dict):
        values['traversal_value'] = self.traversal_func(self, **values)

        if not self.func:
            return self

        if self.func(**values):
            node = self.right_child.traverse(values)
        else:
            node = self.left_child.traverse(values)
        return node

    def traverse_store(self, values:dict, obj_to_store):
        """Traverses the tree but stores the objects in the final node"""
        values['traversal_value'] = self.traversal_func(self, **values)

        if not self.func:
            self.storage.append(obj_to_store)
            return self

        if self.func(**values):
            node = self.right_child.traverse_store(values, obj_to_store)
        else:
            node = self.left_child.traverse_store(values, obj_to_store)
        return node


    def __str__(self):
        return f"{self.description}"


class IrsDecisionTree(object):
    """An IRS decision tree superclass"""
    BRANCHES = ['left_child', "right_child"]

    def __init__(self):
        self.root = IrsDecisionNode(identifier="root", description="root", side=1, if_func=lambda **kwargs: True)
        self.nodes = {"root": self.root}

    def add_branch(self, parent_node, branch, identifier, description, if_func=None,
                   traversal_func=lambda itself, **kwargs: itself.side):
        if isinstance(parent_node, str):
            parent_node = self.nodes[parent_node]
        new_node = IrsDecisionNode(description=description, identifier=identifier,
                        side=branch, if_func=if_func, traversal_func=traversal_func)
        self.nodes[identifier] = new_node
        setattr(parent_node, self.BRANCHES[branch], new_node)

    def connect(self, parent_node, branch, child_identifier):
        """Connects a parent on a particular side to another node already in the tree"""
        parent = self.nodes[parent_node]
        child = self.nodes[child_identifier]
        setattr(parent, self.BRANCHES[branch], child)

    def traverse(self, traversal_value=0, **values):
        values.update({"traversal_value": traversal_value})
        self.root.traverse(values)
        return values['traversal_value']

    def _traverse_store(self, obj_to_store, traversal_value=0, **values):
        """Traverses the tree.  Stores an object in the final node where it winds up.  Then returns that node"""
        values.update({"traversal_value": traversal_value})
        final_node = self.root.traverse_store(values, obj_to_store)
        return final_node

    def traverse_store(self, objects_to_store, param_name):
        final_nodes = set()
        for obj in objects_to_store:
            vals = {param_name: obj}
            node = self._traverse_store(obj, **vals)
            final_nodes.add(node)
        return {node.identifier: node for node in final_nodes}

    def get_final_node(self, traversal_value=0, **values):
        values.update({"traversal_value": traversal_value})
        node = self.root.traverse(values)
        return node.identifier


    def str_decision(self, traversal_value=0, **values):
        values.update({"traversal_value": traversal_value})

        node = self.root.right_child
        my_string = ""
        depth = 0
        while True:
            values['traversal_value'] = node.traversal_func(node, **values)

            my_string += f"{depth * 3 * ' '}{node}"
            if not node.func:
                break

            depth += 1
            if node.func(**values):
                my_string += "-> True\n"
                node = node.right_child
            else:
                my_string += "-> False\n"
                node = node.left_child

        return my_string





