#!/bin/bash

# AlgoTrader Deployment Script for AWS EC2

set -e

echo "🚀 Starting AlgoTrader deployment..."

# Configuration
APP_NAME="alogtrader"
APP_DIR="/opt/$APP_NAME"
SERVICE_USER="alogtrader"
NGINX_CONF="/etc/nginx/sites-available/$APP_NAME"
NGINX_ENABLED="/etc/nginx/sites-enabled/$APP_NAME"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root"
   exit 1
fi

# Update system packages
print_status "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install required packages
print_status "Installing required packages..."
apt-get install -y \
    curl \
    wget \
    git \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    htop \
    unzip

# Start and enable Docker
print_status "Starting Docker service..."
systemctl start docker
systemctl enable docker

# Create application user
print_status "Creating application user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$APP_DIR" -m "$SERVICE_USER"
    usermod -aG docker "$SERVICE_USER"
fi

# Create application directory
print_status "Creating application directory..."
mkdir -p "$APP_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# Clone or update application code
print_status "Setting up application code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    sudo -u "$SERVICE_USER" git pull origin main
else
    # Replace with your actual repository URL
    sudo -u "$SERVICE_USER" git clone https://github.com/yourusername/alogtrader.git "$APP_DIR"
fi

# Set up environment file
print_status "Setting up environment configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/env.example" "$APP_DIR/.env"
    print_warning "Please edit $APP_DIR/.env with your actual configuration values"
fi

# Set up SSL certificates (Let's Encrypt)
print_status "Setting up SSL certificates..."
if [ ! -f "/etc/letsencrypt/live/yourdomain.com/fullchain.pem" ]; then
    print_warning "Please run the following command to get SSL certificates:"
    echo "certbot --nginx -d yourdomain.com"
else
    print_status "SSL certificates already exist"
fi

# Configure Nginx
print_status "Configuring Nginx..."
cp "$APP_DIR/nginx/nginx.conf" "/etc/nginx/sites-available/$APP_NAME"

# Enable the site
ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# Remove default Nginx site
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Create systemd service for the application
print_status "Creating systemd service..."
cat > "/etc/systemd/system/$APP_NAME.service" << EOF
[Unit]
Description=AlgoTrader Application
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker-compose -f docker-compose.prod.yml restart
User=$SERVICE_USER
Group=$SERVICE_USER

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable "$APP_NAME"

# Set up log rotation
print_status "Setting up log rotation..."
cat > "/etc/logrotate.d/$APP_NAME" << EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload $APP_NAME
    endscript
}
EOF

# Set up monitoring script
print_status "Setting up monitoring script..."
cat > "/usr/local/bin/$APP_NAME-monitor.sh" << EOF
#!/bin/bash

# AlgoTrader Health Monitor
APP_NAME="$APP_NAME"
LOG_FILE="/var/log/$APP_NAME-monitor.log"

check_service() {
    if systemctl is-active --quiet "\$APP_NAME"; then
        echo "\$(date): Service is running" >> "\$LOG_FILE"
    else
        echo "\$(date): Service is not running, attempting restart" >> "\$LOG_FILE"
        systemctl restart "\$APP_NAME"
    fi
}

check_health() {
    response=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/health/)
    if [ "\$response" = "200" ]; then
        echo "\$(date): Health check passed" >> "\$LOG_FILE"
    else
        echo "\$(date): Health check failed (HTTP \$response)" >> "\$LOG_FILE"
        systemctl restart "\$APP_NAME"
    fi
}

check_service
check_health
EOF

chmod +x "/usr/local/bin/$APP_NAME-monitor.sh"

# Set up cron job for monitoring
print_status "Setting up monitoring cron job..."
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/$APP_NAME-monitor.sh") | crontab -

# Start services
print_status "Starting services..."
systemctl start nginx
systemctl enable nginx
systemctl start "$APP_NAME"

# Wait for services to start
print_status "Waiting for services to start..."
sleep 30

# Check service status
if systemctl is-active --quiet "$APP_NAME"; then
    print_status "✅ AlgoTrader service is running"
else
    print_error "❌ AlgoTrader service failed to start"
    systemctl status "$APP_NAME"
    exit 1
fi

# Check Nginx status
if systemctl is-active --quiet nginx; then
    print_status "✅ Nginx is running"
else
    print_error "❌ Nginx failed to start"
    systemctl status nginx
    exit 1
fi

# Final status check
print_status "Performing final health check..."
sleep 10

if curl -f -s http://localhost/api/v1/health/ > /dev/null; then
    print_status "✅ Application health check passed"
else
    print_warning "⚠️  Application health check failed - please check logs"
fi

print_status "🎉 Deployment completed successfully!"
print_status "Application is available at: http://yourdomain.com"
print_status "API documentation: http://yourdomain.com/docs"
print_status "Health check: http://yourdomain.com/api/v1/health/"

print_warning "Next steps:"
echo "1. Edit $APP_DIR/.env with your actual configuration"
echo "2. Set up SSL certificates: certbot --nginx -d yourdomain.com"
echo "3. Configure your domain DNS to point to this server"
echo "4. Test the application endpoints"

print_status "Useful commands:"
echo "- Check service status: systemctl status $APP_NAME"
echo "- View logs: journalctl -u $APP_NAME -f"
echo "- Restart service: systemctl restart $APP_NAME"
echo "- View application logs: docker-compose -f $APP_DIR/docker-compose.prod.yml logs -f"
