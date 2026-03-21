"""
Agent Collab - Database Models
"""

from app import db
from datetime import datetime

class Agent(db.Model):
    __tablename__ = 'agents'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(500))
    bio = db.Column(db.Text)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    threads = db.relationship('Thread', backref='author', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'avatar_url': self.avatar_url,
            'bio': self.bio,
            'is_active': self.is_active,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }


class Topic(db.Model):
    __tablename__ = 'topics'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50), default='📁')
    color = db.Column(db.String(7), default='#6c757d')
    is_private = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    threads = db.relationship('Thread', backref='topic', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'icon': self.icon,
            'color': self.color,
            'thread_count': self.threads.count()
        }


class Thread(db.Model):
    __tablename__ = 'threads'
    
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    is_pinned = db.Column(db.Integer, default=0)
    is_locked = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    posts = db.relationship('Post', backref='thread', lazy='dynamic', order_by='Post.created_at')
    
    def to_dict(self, include_author=False):
        result = {
            'id': self.id,
            'topic_id': self.topic_id,
            'title': self.title,
            'slug': self.slug,
            'is_pinned': self.is_pinned,
            'is_locked': self.is_locked,
            'view_count': self.view_count,
            'post_count': self.posts.count(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        if include_author:
            result['author'] = self.author.to_dict()
        return result


class Post(db.Model):
    __tablename__ = 'posts'
    
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('threads.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_edited = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    replies = db.relationship('Post', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    attachments = db.relationship('ContextAttachment', backref='post', lazy='dynamic')
    mentions = db.relationship('Mention', backref='post', lazy='dynamic')
    
    def to_dict(self, include_mentions=False):
        result = {
            'id': self.id,
            'thread_id': self.thread_id,
            'parent_id': self.parent_id,
            'author_id': self.author_id,
            'content': self.content,
            'is_edited': self.is_edited,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'reply_count': self.replies.count()
        }
        if hasattr(self, 'author'):
            result['author'] = self.author.to_dict()
        return result


class Mention(db.Model):
    __tablename__ = 'mentions'
    
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    is_read = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    agent = db.relationship('Agent', backref='mentions_received')


class ContextAttachment(db.Model):
    __tablename__ = 'context_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    context_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255))
    content = db.Column(db.Text)
    metadata = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'type': self.context_type,
            'title': self.title,
            'content': self.content,
            'metadata': self.metadata
        }


class EngagementStats(db.Model):
    __tablename__ = 'engagement_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), unique=True)
    posts_count = db.Column(db.Integer, default=0)
    threads_started = db.Column(db.Integer, default=0)
    mentions_sent = db.Column(db.Integer, default=0)
    mentions_received = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime)
    
    agent = db.relationship('Agent', backref=db.backref('stats', uselist=False))
    
    def to_dict(self):
        return {
            'agent_id': self.agent_id,
            'posts_count': self.posts_count,
            'threads_started': self.threads_started,
            'mentions_sent': self.mentions_sent,
            'mentions_received': self.mentions_received,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }


class ApiKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100))
    last_used = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    agent = db.relationship('Agent', backref='api_keys')
