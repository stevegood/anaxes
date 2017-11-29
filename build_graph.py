import logging as log
from glob import glob
from json import loads
from os import chdir
from py2neo import Graph, Node

# setup logging
log_template = "[%(levelname)s][%(asctime)s] %(message)s"
log.basicConfig(level=log.INFO, format=log_template)

IGNORED_DATA_FILES = [
    "damage-deck-core-tfa.js",
    "damage-deck-core.js",
    "damage-deck-rebel-transport.js",
    "reference-cards.js"
]

# Configure neo4j connection
g = Graph(password="")

# Step 0) Drop all data in the current graph
g.delete_all()

# Step 1) Read data JSON files and create nodes for each item
# Create a transaction to collect all of our changes.
tx = g.begin()
chdir("xwing-data/data")
for filename in glob("*.js"):
    if filename not in IGNORED_DATA_FILES:
        log.info("Opening %s" % filename)
        object_type = filename[:-4].title()
        with open(filename, 'r') as file:
            file_content = file.read()
            items = loads(file_content)
            for item in items:
                log.info("[%s] %s" % (object_type, item["name"]))
                # TODO: create the node for this item
                # Node(**item) should populate the node
                try:
                    node = Node(object_type, **item)
                    tx.create(node)
                except TypeError as e:
                    log.error(e.message)
                    pass

# Write everything we did to the DB
tx.commit()


# Step 2) Create relationships between the nodes based on game rules
