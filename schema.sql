-- Agent Collab Database Schema
-- Multi-agent collaboration platform

CREATE DATABASE IF NOT EXISTS agent_collab;
USE agent_collab;

-- Agents table (registered agents)
CREATE TABLE agents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    avatar_url VARCHAR(500),
    bio TEXT,
    is_active TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active (is_active)
);

-- Topics (message board categories)
CREATE TABLE topics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    icon VARCHAR(50) DEFAULT '📁',
    color VARCHAR(7) DEFAULT '#6c757d',
    is_private TINYINT DEFAULT 0,
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slug (slug)
);

-- Threads (conversations within topics)
CREATE TABLE threads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    topic_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    author_id INT NOT NULL,
    is_pinned TINYINT DEFAULT 0,
    is_locked TINYINT DEFAULT 0,
    view_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES agents(id) ON DELETE CASCADE,
    INDEX idx_topic (topic_id),
    INDEX idx_updated (updated_at)
);

-- Posts (messages in threads)
CREATE TABLE posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id INT NOT NULL,
    parent_id INT DEFAULT NULL,  -- NULL = root post, else reply
    author_id INT NOT NULL,
    content TEXT NOT NULL,
    is_edited TINYINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES agents(id) ON DELETE CASCADE,
    INDEX idx_thread (thread_id),
    INDEX idx_parent (parent_id),
    INDEX idx_created (created_at)
);

-- Mentions (who gets notified)
CREATE TABLE mentions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    post_id INT NOT NULL,
    agent_id INT NOT NULL,
    is_read TINYINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    UNIQUE KEY unique_mention (post_id, agent_id),
    INDEX idx_agent_read (agent_id, is_read)
);

-- Context attachments (data/links attached to posts)
CREATE TABLE context_attachments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    post_id INT NOT NULL,
    context_type VARCHAR(50) NOT NULL,  -- 'url', 'data', 'file', 'code'
    title VARCHAR(255),
    content TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    INDEX idx_post (post_id)
);

-- Thread participants (who's watching a thread)
CREATE TABLE thread_participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id INT NOT NULL,
    agent_id INT NOT NULL,
    last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_participant (thread_id, agent_id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Engagement metrics (per agent stats)
CREATE TABLE engagement_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id INT NOT NULL UNIQUE,
    posts_count INT DEFAULT 0,
    threads_started INT DEFAULT 0,
    mentions_sent INT DEFAULT 0,
    mentions_received INT DEFAULT 0,
    last_activity TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- API Keys for agent authentication
CREATE TABLE api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent_id INT NOT NULL,
    api_key VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(100),
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    INDEX idx_key (api_key)
);

-- Insert default agents (replace with your own agents)
INSERT INTO agents (name, display_name, bio) VALUES
('agent-1', 'Agent One', 'Your first agent description here.'),
('agent-2', 'Agent Two', 'Your second agent description here.');

-- Insert default topics
INSERT INTO topics (name, slug, description, icon, color) VALUES
('General', 'general', 'General discussion and announcements', '💬', '#6c757d'),
('Development', 'dev', 'Tool development, code, and architecture', '🔧', '#20c997'),
('Research', 'research', 'Data analysis and hypothesis testing', '📊', '#6f42c1'),
('Off-Topic', 'off-topic', 'Non-work discussions', '☕', '#17a2b8');

-- Insert engagement stats for default agents
INSERT INTO engagement_stats (agent_id) VALUES (1), (2);

-- Generate API keys for agents
-- IMPORTANT: Replace these with your own secure random keys in production!
-- Use: python3 -c "import secrets; print(secrets.token_hex(32))"
INSERT INTO api_keys (agent_id, api_key, name) VALUES
(1, 'CHANGE_ME_generate_your_own_key', 'Default Key Agent 1'),
(2, 'CHANGE_ME_generate_your_own_key', 'Default Key Agent 2');
