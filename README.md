# GeoSnapPro

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Docker](https://img.shields.io/badge/Docker-Enabled-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**GeoSnapPro** is a robust, microservices-based screenshot service designed for geo-targeted captures. By integrating with VPN services (Gluetun), it allows users to route traffic through various locations to capture screenshots as they appear to users in different regions. It leverages advanced anti-detection techniques to ensure reliable captures even from bot-protected sites.

## 🚀 Key Features

-   **Geo-Targeted Screenshots**: Seamlessly route traffic through VPN tunnels to capture localized content.
-   **Advanced Anti-Detection**: Utilizes **Camoufox** and **Playwright** to mimic real user behavior and evade bot detection systems.
-   **Scalable Microservices Architecture**: Built with Docker Compose, separating concerns between the frontend, screenshot engine, and VPN management.
-   **User-Friendly Interface**: A clean, responsive web interface for managing screenshot requests and viewing results.
-   **VPN Management**: Integrated control over Gluetun for managing VPN connections and IP rotation.

## 🛠️ Technology Stack

### Backend & Core Services
-   **Screenshot Engine**: [FastAPI](https://fastapi.tiangolo.com/) + [Playwright](https://playwright.dev/) + [Camoufox](https://github.com/daijro/camoufox)
-   **VPN Gateway**: [Gluetun](https://github.com/qdm12/gluetun)
-   **API Gateway / VPN Manager**: Flask + Docker SDK

### Frontend
-   **Framework**: Flask (serving HTML/CSS/JS)
-   **Styling**: Custom CSS with a focus on responsiveness and modern aesthetics.

### Infrastructure
-   **Containerization**: Docker & Docker Compose

## 📋 Prerequisites

Before you begin, ensure you have the following installed on your machine:

-   [Docker](https://docs.docker.com/get-docker/)
-   [Docker Compose](https://docs.docker.com/compose/install/)

## 📦 Installation & Getting Started

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/geosnappro-thefinal.git
    cd geosnappro-thefinal
    ```

2.  **Environment Configuration**
    Check the `services/gluetun-api-docker/.env.example` and other service directories for any required environment variables. Typically, the default configuration in `deploy/docker-compose.yml` works out of the box for development.

3.  **Build and Run**
    Navigate to the `deploy` directory and start the services:
    ```bash
    cd deploy
    docker-compose up --build
    ```
    *Note: The first build may take a few minutes as it pulls necessary images and installs dependencies.*

4.  **Access the Application**
    Once the services are running, open your browser and navigate to:
    ```
    http://localhost:5000
    ```

## 📖 Usage

1.  **Dashboard**: Upon logging in (if auth is enabled) or accessing the main page, you will see the dashboard.
2.  **Request Screenshot**: Enter the URL you wish to capture.
3.  **Select Location**: Choose a VPN server location if you want to test geo-specific rendering.
4.  **View Results**: The screenshot will be processed and displayed in the gallery.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1.  Fork the project
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
