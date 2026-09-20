mergeInto(LibraryManager.library, {
  FruitsimAppleNotify: function(callbackNamePtr, valuePtr) {
    var callbackName = UTF8ToString(callbackNamePtr);
    var value = UTF8ToString(valuePtr);
    var callback = window[callbackName];
    if (typeof callback === 'function') callback(value);
  }
});
