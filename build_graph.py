import logging.config
from glob import glob
from json import dumps, loads
from py2neo import Graph, Node, Relationship

# setup logging
logging.config.fileConfig("logging.conf")
log = logging.getLogger("buildGraph")

# Directory in which the data lives
DATA_DIR = "xwing-data/data/"

# filenames to ignore
IGNORED_DATA_FILES = [
    "%ssources.js" % DATA_DIR
]

RELATIONSHIPS = {}
with open("relationships.json", 'r') as relationships_file:
    file_content = relationships_file.read()
    log.debug("Relationships definitions:\n%s", file_content)
    RELATIONSHIPS = loads(file_content)

# Configure neo4j connection
g = Graph(password="")

# Step 0) Drop all data in the current graph
g.delete_all()

# Step 1) Read data JSON files and create nodes for each item
# Step 2) Create relationships between the nodes based on game rules

# Create a transaction to collect all of our changes.
tx = g.begin()

relationships = []
# {
#   'left_node': {
#       'id_name': node_id_field,
#       'id_value': value
#   },
#   'relationship': {
#       'type': relationship_type
#   },
#   'right_node': {
#       'id_name': node_id_field,
#       'id_value': value
#   }
# }

for filename in glob("%s*.js" % DATA_DIR):
    if filename not in IGNORED_DATA_FILES:
        log.info("Opening [%s]", filename)
        
        object_type = filename.replace(DATA_DIR, "")[:-3].title()
        if object_type.endswith("s"):
            object_type = object_type[:-1]
        object_type = object_type.replace("-", "")

        object_type_relationships = RELATIONSHIPS[object_type] if object_type in RELATIONSHIPS else {}

        with open(filename, 'r') as data_file:
            file_content = data_file.read()
            items = loads(file_content)
            for item in items:
                name = item["title"] if "title" in item else item["name"]
                log.info("Creating [%s] node for [%s]", object_type, name)

                # process the item, looking for nested dicts and lists
                p_item = {}
                node_relationships = []
                for key, value in item.iteritems():
                    if type(value) is dict or type(value) is list:
                        s_value = dumps(value)
                        # Found a list or dict. For now, serialize it and persist.
                        # In the future, create a relationship for this.
                        if key in object_type_relationships:
                            field_relationship = object_type_relationships[key]
                            if field_relationship["serialize"] is True:
                                log.debug("serializing [%s]: %s", key, s_value)
                                p_item[key] = s_value
                            else:
                                node_type = field_relationship["type"]
                                relationship_type = field_relationship["relationship"]
                                data_type = field_relationship["dataType"]
                                id_field = field_relationship["idField"]
                                log.debug("Found relationship mapping for [%s]. (:%s)-[:%s]->(:%s)",
                                          key, object_type, relationship_type, node_type)

                                if data_type == "array":
                                    log.debug("Processing %s as %s", key, data_type)
                                    for id_value in value:
                                        log.debug("(:%s)-[:%s]->(:%s{%s: %s})",
                                                  object_type, relationship_type, node_type, id_field, id_value)
                                        related_node = g.find_one(node_type, id_field, id_value)
                                        if not related_node:
                                            log.debug("Didn't find a %s with %s == %s so I'm creating it",
                                                      node_type, id_field, id_value)
                                            r_data = {id_field: id_value}
                                            related_node = Node(node_type, **r_data)
                                            tx.create(related_node)
                                            tx.commit()
                                            tx = g.begin()

                                        node_relationships.append({
                                            'relationship': {
                                                'type': relationship_type
                                            },
                                            'right_node': {
                                                'type': node_type,
                                                'id_name': id_field,
                                                'id_value': id_value
                                            }
                                        })
                        else:
                            log.warn("serializing [%s]: %s", key, s_value)
                            p_item[key] = s_value
                    else:
                        if key in object_type_relationships:
                            field_relationship = object_type_relationships[key]
                            if field_relationship['serialize']:
                                p_item[key] = dumps(value)
                            else:
                                if field_relationship['relationshipOnly']:
                                    node_type = field_relationship['type']
                                    relationship_type = field_relationship['relationship']
                                    related_node_id_field = field_relationship['relatedNodeIdField']
                                    node_relationships.append({
                                        'relationship': {
                                            'type': relationship_type
                                        },
                                        'right_node': {
                                            'type': node_type,
                                            'id_name': related_node_id_field,
                                            'id_value': value
                                        }
                                    })
                        else:
                            p_item[key] = value

                # create the node for this item
                # Node(**item) should populate the node
                try:
                    node = Node(object_type, **p_item)
                    tx.create(node)
                    for relationship in node_relationships:
                        relationship['left_node'] = {
                            'type': object_type,
                            'id_name': 'id',
                            'id_value': p_item['id']
                        }
                        relationships.append(relationship)
                except TypeError as e:
                    log.error(e.message)
                    pass

for relationship in relationships:
    left_node_id_name = relationship['left_node']['id_name']
    left_node_id_value = relationship['left_node']['id_value']
    left_node_type = relationship['left_node']['type']
    left_node = g.find_one(left_node_type, left_node_id_name, left_node_id_value)

    rel_type = relationship['relationship']['type']

    right_node_id_name = relationship['right_node']['id_name']
    right_node_id_value = relationship['right_node']['id_value']
    right_node_type = relationship['right_node']['type']
    right_node = g.find_one(right_node_type, right_node_id_name, right_node_id_value)

    if left_node and right_node:
        log.debug("Creating relationship: (:%s{%s: '%s'})-[:%s]->(:%s{%s: '%s'})",
                  left_node_type, left_node_id_name, left_node_id_value, rel_type,
                  right_node_type, right_node_id_name, right_node_id_value)
        rel = Relationship(left_node, rel_type, right_node)
        tx.create(rel)

# Write everything we did to the DB
log.debug("Commiting transaction")
tx.commit()

log.info("Done!")
