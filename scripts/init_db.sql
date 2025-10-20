# Database initialization script
CREATE DATABASE alogtrader;

-- Create user and grant permissions
CREATE USER alogtrader WITH PASSWORD 'alogtrader_password';
GRANT ALL PRIVILEGES ON DATABASE alogtrader TO alogtrader;

-- Connect to the database
\c alogtrader;

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO alogtrader;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO alogtrader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO alogtrader;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO alogtrader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO alogtrader;
