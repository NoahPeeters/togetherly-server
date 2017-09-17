import socket
import sys
from thread import start_new_thread
import time
from pyparsing import *
from random import random
import os
import colorsys

BASE_PATH = '/var/togetherly-server/'
HOST = '' # all availabe interfaces
PORT = 10000

clients = []
fileHandlers = {}

class FileHandler:
    def __init__(self, path):
        self.path = path
        self.text = ""
        self.clients = []
        if os.path.isfile(self.path):
            self.text = open(self.path).read()

    def addClient(self, client):
        self.clients.append(client)
    
    def removeClient(self, client):
        self.clients.remove(client)

    def broadcast(self, msg):
        for client in self.clients:
            client.conn.sendall(msg)

    def updateCursorPositions(self):
        msg = "(cursors " + " ".join([client.cursorsUpdateString() for client in self.clients]) + ")"
        self.broadcast(msg)

    def readText(self):
        return self.text

    def writeText(self, text):
        self.text = text
        open(self.path, "w").write(text)


def getFileHandler(fileName):
    path = os.path.normpath(os.path.join(BASE_PATH, fileName))

    if not path.startswith(BASE_PATH):
        return None

    dirname = os.path.dirname(path)
    if not os.path.isdir(dirname):
        os.mkdir(dirname)

    if path in fileHandlers:
        return fileHandlers[path]
    else:
        fileHandler = FileHandler(path)
        fileHandlers[path] = fileHandler
        return fileHandler

ParserElement.setDefaultWhitespaceChars(' ')
def parseMessageData(data):
    lists = []
    currentList = []
    currentItem = ""
    listString = ""
    inList = False
    inQuote = False
    charIndex = 0

    l = len(data)
    while charIndex < l:
        char = data[charIndex]
        listString += char
        if not inList:
            if char == "(":
                inList = True
                currentList = []
                currentItem = ""
        elif char == "\\":
            charIndex += 1
            currentItem += data[charIndex]
            listString += data[charIndex]
        elif inQuote:
            if char == "\"":
                inQuote = False
            else:
                currentItem += char
        elif char == ")":
            inList = False
            currentList.append(currentItem)
            lists.append((currentList, listString))
            listString = ""
        elif char == "\"":
            inQuote = True
        elif char == " ":
            currentList.append(currentItem)
            currentItem = ""
        else:
            currentItem += char
        charIndex += 1


    return lists
    return OneOrMore(nestedExpr()).parseString(data)

def hsv_to_hex(h, s, v):
    rgb = colorsys.hsv_to_rgb(h, s, v)
    return '#%02X%02X%02X' % (rgb[0] * 255.0, rgb[1] * 255.0, rgb[2] * 255.0)

def randomColors():
    h = random()
    return (hsv_to_hex(h, 1.0, 0.6), hsv_to_hex(h, 1.0, 0.25))

def broadcast(msg):
    for client in clients:
        client.conn.sendall(msg)

def updateCursorPositions():
    for fileHandler in fileHandlers.values():
        fileHandler.updateCursorPositions()

def updateCursorPositionsThread():
    while True:
        updateCursorPositions()
        time.sleep(0.5)


def main():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error, msg:
        print("Could not create socket. Error Code: ", str(msg[0]), "Error: ", msg[1])
        sys.exit(0)

    print("[-] Socket Created")

    # bind socket
    try:
        s.bind((HOST, PORT))
        print("[-] Socket Bound to port " + str(PORT))
    except socket.error, msg:
        print("Bind Failed. Error Code: {} Error: {}".format(str(msg[0]), msg[1]))
        sys.exit()

    s.listen(10)
    print("Listening...")

    start_new_thread(updateCursorPositionsThread, ())

    while True:
        # blocking call, waits to accept a connection
        conn, addr = s.accept()
        print("[-] Connected to " + addr[0] + ":" + str(addr[1]))

        start_new_thread(client_thread, (conn,))



class Client:
    def __init__(self, conn):
        self.conn = conn
        colors = randomColors()
        self.pcolor = colors[0]
        self.rcolor = colors[1]
        self.mark = "nil"
        self.position = "0"
        self.name = ""
        self.fileHandle = None

    def cursorsUpdateString(self):
        return "(\"" + self.name + "\" \"" + self.rcolor + "\" \"" + self.pcolor + "\" " + self.mark + " . " + self.position + ")"

    def sendWelcomeMessage(self):
        text = self.fileHandler.readText()
        self.conn.sendall("(welcome \"" + text + "\" . org-mode)")

    def sendError(self, msg):
        self.conn.sendall("(error \"" + msg + "\")")

    def parseMessage(self, messageObject):
        message = messageObject[0]
        command = message[0]

        if command == "login":
            self.name = message[1]
            self.fileHandler = getFileHandler(message[3])

            if self.fileHandler is None:
                self.close()
                return

            self.fileHandler.addClient(self)
            clients.append(self)
            self.sendWelcomeMessage()
        elif command == "moved":
            self.mark = message[1]
            self.position = message[3]
        elif command == "refresh":
            self.sendWelcomeMessage()
        elif command == "changed":
            beg = int(message[2]) - 1 # python starts counting with 0
            beforeString = message[3]
            afterString = message[5]
            bSLen = len(beforeString)
            end = beg+bSLen


            text = self.fileHandler.readText()
            if text[beg:end] == beforeString:
                text = text[:beg] + afterString + text[end:]
                self.fileHandler.broadcast(messageObject[1])
                self.fileHandler.writeText(text)
            else:
                print("something went wrong")
                self.sendWelcomeMessage()
        else:
            print(message)


    def parseData(self, data):
        for message in parseMessageData(data):
            self.parseMessage(message)

    def close(self):
        self.conn.close()
        clients.remove(self)
        self.fileHandler.removeClient(self)

    def run(self):
        while True:
            data = self.conn.recv(1024)
            if not data:
                break

            try:
                self.parseData(data)
            except Exception as e:
                self.sendError(str(e))


        self.close()



def client_thread(conn):
    c = Client(conn)
    c.run()


main()


#data = '(changed "Anonymous" 9 "9" . "")'
#print(data)
#print(parseMessageData(data)[0][0])
