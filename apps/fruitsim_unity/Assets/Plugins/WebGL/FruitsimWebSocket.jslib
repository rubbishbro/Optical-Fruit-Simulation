mergeInto(LibraryManager.library, {
  FruitsimWebSocketConnect: function(objectNamePtr, urlPtr) {
    var objectName = UTF8ToString(objectNamePtr);
    var url = UTF8ToString(urlPtr);
    if (!window.fruitsimWebSockets) window.fruitsimWebSockets = {};
    var previous = window.fruitsimWebSockets[objectName];
    if (previous) previous.close();
    var socket = new WebSocket(url);
    window.fruitsimWebSockets[objectName] = socket;
    socket.onopen = function() {
      SendMessage(objectName, "OnWebSocketOpened", "open");
    };
    socket.onmessage = function(event) {
      if (typeof event.data === "string") {
        SendMessage(objectName, "OnWebSocketMessage", event.data);
      }
    };
    socket.onerror = function() {
      SendMessage(objectName, "OnWebSocketError", "WebSocket connection error");
    };
    socket.onclose = function() {
      SendMessage(objectName, "OnWebSocketClosed", "closed");
      delete window.fruitsimWebSockets[objectName];
    };
  },
  FruitsimWebSocketSend: function(objectNamePtr, messagePtr) {
    var objectName = UTF8ToString(objectNamePtr);
    var message = UTF8ToString(messagePtr);
    var socket = window.fruitsimWebSockets && window.fruitsimWebSockets[objectName];
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(message);
  },
  FruitsimWebSocketDisconnect: function(objectNamePtr) {
    var objectName = UTF8ToString(objectNamePtr);
    var socket = window.fruitsimWebSockets && window.fruitsimWebSockets[objectName];
    if (socket) socket.close();
  }
});
