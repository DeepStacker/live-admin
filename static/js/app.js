// Additional JavaScript functionality
class UptimeMonitor {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.init();
  }

  init() {
    this.connectWebSocket();
    this.setupEventListeners();
    this.startPeriodicUpdates();
  }

  connectWebSocket() {
    try {
      this.ws = new WebSocket(`ws://${window.location.host}/ws`);

      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.reconnectAttempts = 0;
        this.updateConnectionStatus(true);
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.handleWebSocketMessage(data);
      };

      this.ws.onclose = () => {
        console.log("WebSocket disconnected");
        this.updateConnectionStatus(false);
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
      };
    } catch (error) {
      console.error("Failed to connect WebSocket:", error);
      this.attemptReconnect();
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        console.log(
          `Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`
        );
        this.connectWebSocket();
      }, 5000 * this.reconnectAttempts);
    }
  }

  handleWebSocketMessage(data) {
    if (data.type === "ping_result") {
      this.updateServiceStatus(data);
    }
  }

  updateServiceStatus(data) {
    // Implementation for updating service status in real-time
    const serviceCard = document.querySelector(
      `[data-service-id="${data.service_id}"]`
    );
    if (serviceCard) {
      // Update visual indicators
      this.animateStatusChange(serviceCard, data.status);
    }
  }

  animateStatusChange(element, status) {
    element.classList.add("pulse");
    setTimeout(() => {
      element.classList.remove("pulse");
    }, 1000);
  }

  updateConnectionStatus(connected) {
    const indicator = document.getElementById("liveStatus");
    if (indicator) {
      if (connected) {
        indicator.innerHTML =
          '<span class="live-indicator bg-success"></span>Live';
        indicator.className = "badge bg-success me-2";
      } else {
        indicator.innerHTML =
          '<span class="live-indicator bg-danger"></span>Disconnected';
        indicator.className = "badge bg-danger me-2";
      }
    }
  }

  setupEventListeners() {
    // Add keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.key === "r") {
        e.preventDefault();
        location.reload();
      }
    });
  }

  startPeriodicUpdates() {
    // Update statistics every 30 seconds
    setInterval(() => {
      this.updateStatistics();
    }, 30000);
  }

  updateStatistics() {
    fetch("/api/services")
      .then((response) => response.json())
      .then((services) => {
        const stats = this.calculateStats(services);
        this.updateStatsDashboard(stats);
      })
      .catch((error) => console.error("Error updating statistics:", error));
  }

  calculateStats(services) {
    return {
      total: services.length,
      online: services.filter((s) => s.enabled && s.last_status === "success")
        .length,
      offline: services.filter((s) => s.enabled && s.last_status !== "success")
        .length,
      disabled: services.filter((s) => !s.enabled).length,
    };
  }

  updateStatsDashboard(stats) {
    const elements = {
      total: document.getElementById("totalServices"),
      online: document.getElementById("onlineServices"),
      offline: document.getElementById("offlineServices"),
      disabled: document.getElementById("disabledServices"),
    };

    Object.keys(elements).forEach((key) => {
      if (elements[key]) {
        elements[key].textContent = stats[key];
      }
    });
  }
}

// Initialize the monitor when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  new UptimeMonitor();
});
