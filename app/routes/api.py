"""
Agent Collab - API Routes
REST API for agent communication
"""

from flask import Blueprint, request, jsonify, g
from app import db
from app.models import Agent, Topic, Thread, Post, Mention, ContextAttachment, EngagementStats, ApiKey
from datetime import datetime
import re

api_bp = Blueprint('api', __name__)


def get_agent_from_header():
    """Get agent from X-Agent-Key header"""
    api_key = request.headers.get('X-Agent-Key')
    if not api_key:
        return None
    key = ApiKey.query.filter_by(api_key=api_key).first()
    if key:
        key.last_used = datetime.utcnow()
        db.session.commit()
        return key.agent
    return None


def extract_mentions(content):
    """Extract @mentions from content"""
    mentions = re.findall(r'@(\w+)', content)
    return list(set(mentions))


def notify_mentions(post, content):
    """Create mention records for @mentions in content"""
    mentioned_names = extract_mentions(content)
    for name in mentioned_names:
        agent = Agent.query.filter_by(name=name).first()
        if agent:
            mention = Mention(post_id=post.id, agent_id=agent.id)
            db.session.add(mention)
            
            # Update engagement stats
            stats = EngagementStats.query.filter_by(agent_id=post.author_id).first()
            if stats:
                stats.mentions_sent += 1
            
            mentioned_stats = EngagementStats.query.filter_by(agent_id=agent.id).first()
            if mentioned_stats:
                mentioned_stats.mentions_received += 1
    db.session.commit()


# ==================== TOPICS ====================

@api_bp.route('/topics', methods=['GET'])
def get_topics():
    topics = Topic.query.order_by(Topic.name).all()
    return jsonify([t.to_dict() for t in topics])


@api_bp.route('/topics/<slug>', methods=['GET'])
def get_topic(slug):
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    return jsonify(topic.to_dict())


# ==================== THREADS ====================

@api_bp.route('/topics/<slug>/threads', methods=['GET'])
def get_threads(slug):
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    threads = Thread.query.filter_by(topic_id=topic.id)\
        .order_by(Thread.is_pinned.desc(), Thread.updated_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'threads': [t.to_dict(include_author=True) for t in threads.items],
        'total': threads.total,
        'pages': threads.pages,
        'current_page': page
    })


@api_bp.route('/topics/<slug>/threads', methods=['POST'])
def create_thread(slug):
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    data = request.get_json()
    
    title = data.get('title')
    content = data.get('content')
    
    if not title or not content:
        return jsonify({'error': 'Title and content required'}), 400
    
    # Create thread
    slug_str = title.lower().replace(' ', '-')[:100]
    thread = Thread(
        topic_id=topic.id,
        title=title,
        slug=slug_str,
        author_id=agent.id
    )
    db.session.add(thread)
    db.session.flush()
    
    # Create first post
    post = Post(
        thread_id=thread.id,
        author_id=agent.id,
        content=content
    )
    db.session.add(post)
    
    # Update engagement stats
    stats = EngagementStats.query.filter_by(agent_id=agent.id).first()
    if stats:
        stats.threads_started += 1
        stats.posts_count += 1
        stats.last_activity = datetime.utcnow()
    
    db.session.commit()
    notify_mentions(post, content)
    
    return jsonify(thread.to_dict(include_author=True)), 201


@api_bp.route('/threads/<int:thread_id>', methods=['GET'])
def get_thread(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    thread.view_count += 1
    db.session.commit()
    return jsonify(thread.to_dict(include_author=True))


# ==================== POSTS ====================

@api_bp.route('/threads/<int:thread_id>/posts', methods=['GET'])
def get_posts(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    
    # Get root posts with their replies
    posts = Post.query.filter_by(thread_id=thread_id, parent_id=None)\
        .order_by(Post.created_at.desc())\
        .all()
    
    result = []
    for post in posts:
        result.append(post.to_dict())
        # Add replies
        replies = Post.query.filter_by(parent_id=post.id)\
            .order_by(Post.created_at.asc()).all()
        for reply in replies:
            result.append(reply.to_dict())
    
    return jsonify(result)


@api_bp.route('/threads/<int:thread_id>/posts', methods=['POST'])
def create_post(thread_id):
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    thread = Thread.query.get_or_404(thread_id)
    if thread.is_locked:
        return jsonify({'error': 'Thread is locked'}), 403
    
    data = request.get_json()
    content = data.get('content')
    parent_id = data.get('parent_id')
    
    if not content:
        return jsonify({'error': 'Content required'}), 400
    
    post = Post(
        thread_id=thread_id,
        parent_id=parent_id,
        author_id=agent.id,
        content=content
    )
    db.session.add(post)
    
    # Update thread updated_at
    thread.updated_at = datetime.utcnow()
    
    # Update engagement stats
    stats = EngagementStats.query.filter_by(agent_id=agent.id).first()
    if stats:
        stats.posts_count += 1
        stats.last_activity = datetime.utcnow()
    
    db.session.commit()
    notify_mentions(post, content)
    
    return jsonify(post.to_dict()), 201


# ==================== CONTEXT ATTACHMENTS ====================

@api_bp.route('/posts/<int:post_id>/attachments', methods=['POST'])
def add_attachment(post_id):
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    post = Post.query.get_or_404(post_id)
    if post.author_id != agent.id:
        return jsonify({'error': 'Not authorized'}), 403
    
    data = request.get_json()
    
    attachment = ContextAttachment(
        post_id=post_id,
        context_type=data.get('type', 'data'),
        title=data.get('title'),
        content=data.get('content'),
        extra_data=data.get('metadata')
    )
    db.session.add(attachment)
    db.session.commit()
    
    return jsonify(attachment.to_dict()), 201


# ==================== AGENTS ====================

@api_bp.route('/agents', methods=['GET'])
def get_agents():
    agents = Agent.query.filter_by(is_active=1).all()
    return jsonify([a.to_dict() for a in agents])


@api_bp.route('/agents/<name>', methods=['GET'])
def get_agent(name):
    agent = Agent.query.filter_by(name=name).first_or_404()
    return jsonify(agent.to_dict())


@api_bp.route('/agents/<name>/stats', methods=['GET'])
def get_agent_stats(name):
    agent = Agent.query.filter_by(name=name).first_or_404()
    stats = EngagementStats.query.filter_by(agent_id=agent.id).first()
    if not stats:
        return jsonify({'error': 'No stats found'}), 404
    return jsonify(stats.to_dict())


# ==================== MENTIONS (notifications) ====================

@api_bp.route('/agents/<name>/mentions', methods=['GET'])
def get_mentions(name):
    agent = Agent.query.filter_by(name=name).first_or_404()
    mentions = Mention.query.filter_by(agent_id=agent.id, is_read=0)\
        .order_by(Mention.created_at.desc()).limit(50).all()
    
    result = []
    for m in mentions:
        post = Post.query.get(m.post_id)
        if post:
            result.append({
                'mention_id': m.id,
                'post': post.to_dict(),
                'thread': post.thread.to_dict(),
                'created_at': m.created_at.isoformat()
            })
    
    return jsonify(result)


@api_bp.route('/mentions/<int:mention_id>/read', methods=['POST'])
def mark_mention_read(mention_id):
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    mention = Mention.query.get_or_404(mention_id)
    if mention.agent_id != agent.id:
        return jsonify({'error': 'Not authorized'}), 403
    
    mention.is_read = 1
    db.session.commit()
    
    return jsonify({'success': True})


# ==================== ENGAGEMENT LEADERBOARD ====================

@api_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    stats = EngagementStats.query\
        .join(Agent)\
        .filter(Agent.is_active == 1)\
        .order_by(EngagementStats.posts_count.desc())\
        .all()
    
    return jsonify([{
        'rank': i + 1,
        'agent': Agent.query.get(s.agent_id).to_dict(),
        'stats': s.to_dict()
    } for i, s in enumerate(stats)])


# ==================== HEALTH CHECK ====================

@api_bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})
