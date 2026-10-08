// Globally loaded reCamera Pro icon set for Home Assistant navigation.
window.customIconsets = window.customIconsets || {};
window.customIconsets.recamera = async iconName => {
  if (iconName !== "pro") return {};
  return {
    viewBox: "0 0 24 24",
    path: "M3 7.4 11.4 2.5 21 7.8v8.5l-9.4 5.2L3 16.5V7.4m8.4-2.6L5.6 8.2l5.9 3.3L18 7.9l-6.6-3.1M5 9.8v5.6l6.5 3.7v-5.7L5 9.8m8.2 3.4v5.6l5.8-3.3V10l-5.8 3.2M8.3 11a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2m0 1.5a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2"
  };
};

// Notify already-rendered ha-icon elements after a late frontend reload.
window.dispatchEvent(new Event("iron-iconset-added"));
