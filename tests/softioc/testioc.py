from pcaspy import Driver, SimpleServer

# Define your PVs, including an array PV
pvdb = {
    "MY:PV:SIMPLE": {
        "type": "float",
        "prec": 3,
    },
    "MY:PV:STATUS": {
        "type": "enum",
        "enums": ["Off", "On"],
    },
    "MY:PV:ARRAY": {  # This PV is defined as an array of floats
        "type": "float",
        "count": 10,  # Specify the number of elements in the array
        "value": [0.0] * 10,  # Initialize with zeros
    },
}


class MyDriver(Driver):
    def __init__(self):
        super(MyDriver, self).__init__()


server = SimpleServer()
server.createPV("", pvdb)
driver = MyDriver()

while True:
    server.process(0.1)
