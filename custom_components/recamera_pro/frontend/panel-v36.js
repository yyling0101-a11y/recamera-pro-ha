// reCamera Pro device manager v36
window.customIconsets = window.customIconsets || {};
window.customIconsets.recamera = async iconName => {
  if (iconName !== "pro") return {};
  return {
    viewBox: "0 0 24 24",
    path: "M3 7.4 11.4 2.5 21 7.8v8.5l-9.4 5.2L3 16.5V7.4m8.4-2.6L5.6 8.2l5.9 3.3L18 7.9l-6.6-3.1M5 9.8v5.6l6.5 3.7v-5.7L5 9.8m8.2 3.4v5.6l5.8-3.3V10l-5.8 3.2M8.3 11a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2m0 1.5a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2"
  };
};

if (!window.__recameraProV36Loaded && !customElements.get("recamera-pro")) {
  window.__recameraProV36Loaded = true;
  customElements.define("recamera-pro", class extends HTMLElement {
    set hass(value) {
      this._hass = value;
      this._sendAuth();
    }

    _currentToken() {
      return this._hass?.auth?.accessToken
        || this._hass?.auth?.data?.access_token
        || "";
    }

    async _sendAuth(forceRefresh = false) {
      if (forceRefresh && typeof this._hass?.auth?.refreshAccessToken === "function") {
        try {
          await this._hass.auth.refreshAccessToken();
        } catch (error) {
          // The current token may still be usable; let the iframe decide.
        }
      }
      const token = this._currentToken();
      if (token && this._frame?.contentWindow) {
        this._frame.contentWindow.postMessage(
          {type: "recamera-auth", token},
          location.origin
        );
      }
    }

    connectedCallback() {
      this.style.cssText = "display:block;height:100%";
      this.innerHTML = '<iframe src="/recamera_pro_static/panel-v36.html?v=3.9.2" style="width:100%;height:100%;border:0;display:block"></iframe>';
      this._frame = this.querySelector("iframe");
      this._fitHeight = () => {
        const top = this.getBoundingClientRect().top;
        this.style.height = `${Math.max(240, window.innerHeight - top)}px`;
      };
      this._fitHeight();
      this._onMessage = event => {
        if (
          event.origin === location.origin
          && event.source === this._frame.contentWindow
          && ["recamera-ready", "recamera-auth-request"].includes(event.data?.type)
        ) {
          this._sendAuth(event.data?.type === "recamera-auth-request");
        }
      };
      this._frame.addEventListener("load", () => {
        this._fitHeight();
        this._sendAuth();
      });
      window.addEventListener("message", this._onMessage);
      window.addEventListener("resize", this._fitHeight);
      this._resizeObserver = new ResizeObserver(() => this._fitHeight());
      if (this.parentElement) this._resizeObserver.observe(this.parentElement);
      this._authTimer = window.setInterval(() => this._sendAuth(), 30000);
    }

    disconnectedCallback() {
      window.removeEventListener("message", this._onMessage);
      window.removeEventListener("resize", this._fitHeight);
      if (this._resizeObserver) this._resizeObserver.disconnect();
      window.clearInterval(this._authTimer);
    }
  });
}

