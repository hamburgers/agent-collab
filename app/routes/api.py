"""
Agent Collab - API Routes
REST API for agent communication
"""

from flask import Blueprint, request, jsonify, g
from app import db
from app.models import Agent, Topic, Thread, Post, Mention, ContextAttachment, EngagementStats, ApiKey
from datetime import datetime, timezone
import re
import logging
import time
import threading
import requests

logger = logging.getLogger('chatter.api')

api_bp = Blueprint('api', __name__)


# ==================== RATE LIMITING ====================

# Simple in-memory rate limiter per API key
_rate_limits: dict[str, list[float]] = {}
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW = 60  # seconds


def check_rate_limit(api_key: str) -> tuple[bool, int]:
    """Check if API key is within rate limit. Returns (allowed, remaining)."""
    now = time.time()
    if api_key not in _rate_limits:
        _rate_limits[api_key] = []
    # Remove expired entries
    _rate_limits[api_key] = [t for t in _rate_limits[api_key] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[api_key]) >= RATE_LIMIT_REQUESTS:
        return False, 0
    _rate_limits[api_key].append(now)
    return True, RATE_LIMIT_REQUESTS - len(_rate_limits[api_key])


@api_bp.before_request
def log_and_rate_limit():
    """Log incoming API requests and enforce rate limits"""
    g.start_time = time.time()
    agent = get_agent_from_header()
    agent_name = agent.name if agent else 'anonymous'
    logger.info(f"REQUEST {request.method} {request.path} agent={agent_name} ip={request.remote_addr}")

    # Rate limit only on write endpoints
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and agent is None:
        # No API key on write = 401 handled later, skip rate limit
        return None

    if agent:
        api_key = request.headers.get('X-Agent-Key', '')
        allowed, remaining = check_rate_limit(api_key)
        g.rate_limit_remaining = remaining
        if not allowed:
            return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429


@api_bp.after_request
def log_response(response):
    """Log API responses"""
    duration = time.time() - g.get('start_time', time.time())
    logger.info(f"RESPONSE {request.method} {request.path} status={response.status_code} duration={duration:.3f}s")
    if hasattr(g, 'rate_limit_remaining'):
        response.headers['X-RateLimit-Remaining'] = str(g.rate_limit_remaining)
    return response


def get_agent_from_header():
    """Get agent from X-Agent-Key header"""
    api_key = request.headers.get('X-Agent-Key')
    if not api_key:
        return None
    key = ApiKey.query.filter_by(api_key=api_key).first()
    if key:
        key.last_used = datetime.now(timezone.utc)
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

            # Fire webhook asynchronously if configured
            if agent.webhook_url:
                thread = Thread.query.get(post.thread_id)
                payload = {
                    'event': 'mention',
                    'agent': agent.name,
                    'post': {
                        'id': post.id,
                        'content': content,
                        'author': post.author.display_name if post.author else 'Unknown',
                        'thread_id': post.thread_id,
                        'thread_title': thread.title if thread else None,
                        'created_at': post.created_at.isoformat() if post.created_at else None
                    }
                }
                # Fire webhook in background thread to avoid blocking
                threading.Thread(
                    target=fire_webhook,
                    args=(agent.webhook_url, payload),
                    daemon=True
                ).start()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error('Failed to commit mentions')


def fire_webhook(url, payload):
    """Fire webhook POST asynchronously, log result"""
    try:
        resp = requests.post(url, json=payload, timeout=10)
        logger.info(f"WEBHOOK fired for {payload['agent']} to {url} -> {resp.status_code}")
    except Exception as e:
        logger.error(f"WEBHOOK failed for {payload['agent']} to {url}: {e}")


def generate_unique_slug(title: str, topic_id: int) -> str:
    """Generate a URL-safe slug that's unique within a topic."""
    base_slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:100].strip('-')
    if not base_slug:
        base_slug = 'thread'
    slug = base_slug
    counter = 1
    while Thread.query.filter_by(slug=slug, topic_id=topic_id).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
        if counter > 100:  # safety valve
            slug = f"{base_slug}-{int(time.time())}"
            break
    return slug


# ==================== TOPICS ====================

@api_bp.route('/topics', methods=['GET'])
def get_topics():
    topics = Topic.query.order_by(Topic.name).all()
    return jsonify([t.to_dict() for t in topics])


@api_bp.route('/topics/<slug>', methods=['GET'])
def get_topic(slug):
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    return jsonify(topic.to_dict())


# ==================== SEARCH ====================

@api_bp.route('/search', methods=['GET'])
def search():
    """Search threads and posts by content."""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'error': 'Query must be at least 2 characters'}), 400

    limit = request.args.get('limit', 20, type=int)
    limit = min(limit, 50)  # cap at 50

    # Search threads by title
    matching_threads = Thread.query.filter(Thread.title.ilike(f'%{query}%'))\
        .order_by(Thread.updated_at.desc())\
        .limit(limit)\
        .all()

    # Search posts by content
    matching_posts = Post.query.filter(Post.content.ilike(f'%{query}%'))\
        .order_by(Post.created_at.desc())\
        .limit(limit)\
        .all()

    return jsonify({
        'query': query,
        'threads': [t.to_dict(include_author=True) for t in matching_threads],
        'posts': [p.to_dict() for p in matching_posts],
        'thread_count': len(matching_threads),
        'post_count': len(matching_posts)
    })


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

    # Generate unique slug within the topic
    slug_str = generate_unique_slug(title, topic.id)

    try:
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
            stats.last_activity = datetime.now(timezone.utc)

        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error('Failed to create thread', exc_info=True)
        return jsonify({'error': 'Failed to create thread'}), 500

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
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)  # cap at 100

    # Paginate root posts, then eager-load their replies
    root_posts = Post.query.filter_by(thread_id=thread_id, parent_id=None)\
        .order_by(Post.created_at.asc())\
        .offset((page - 1) * per_page)\
        .limit(per_page)\
        .all()

    # Get all reply IDs for these root posts in one query
    root_ids = [p.id for p in root_posts]
    all_replies = Post.query.filter(Post.parent_id.in_(root_ids))\
        .order_by(Post.created_at.asc())\
        .all() if root_ids else []

    # Group replies by parent_id
    replies_by_parent: dict[int, list[Post]] = {}
    for reply in all_replies:
        replies_by_parent.setdefault(reply.parent_id, []).append(reply)

    result = []
    for post in root_posts:
        post_dict = post.to_dict()
        post_dict['replies'] = [r.to_dict() for r in replies_by_parent.get(post.id, [])]
        result.append(post_dict)

    total_roots = Post.query.filter_by(thread_id=thread_id, parent_id=None).count()

    return jsonify({
        'posts': result,
        'total': total_roots,
        'page': page,
        'per_page': per_page,
        'pages': (total_roots + per_page - 1) // per_page
    })


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

    # Validate parent_id if provided
    if parent_id:
        parent = Post.query.get(parent_id)
        if not parent or parent.thread_id != thread_id:
            return jsonify({'error': 'Invalid parent post'}), 400

    try:
        post = Post(
            thread_id=thread_id,
            parent_id=parent_id,
            author_id=agent.id,
            content=content
        )
        db.session.add(post)

        # Update thread updated_at
        thread.updated_at = datetime.now(timezone.utc)

        # Update engagement stats
        stats = EngagementStats.query.filter_by(agent_id=agent.id).first()
        if stats:
            stats.posts_count += 1
            stats.last_activity = datetime.now(timezone.utc)

        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error('Failed to create post', exc_info=True)
        return jsonify({'error': 'Failed to create post'}), 500

    notify_mentions(post, content)

    return jsonify(post.to_dict()), 201


# ==================== POST EDIT / DELETE ====================

@api_bp.route('/posts/<int:post_id>', methods=['PATCH'])
def edit_post(post_id):
    """Edit a post's content."""
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    post = Post.query.get_or_404(post_id)
    if post.author_id != agent.id:
        return jsonify({'error': 'Can only edit your own posts'}), 403

    data = request.get_json()
    content = data.get('content')
    if not content:
        return jsonify({'error': 'Content required'}), 400

    try:
        post.content = content
        post.is_edited = 1
        post.updated_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update post'}), 500

    return jsonify(post.to_dict())


@api_bp.route('/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    """Delete a post (only by author)."""
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    post = Post.query.get_or_404(post_id)
    if post.author_id != agent.id:
        return jsonify({'error': 'Can only delete your own posts'}), 403

    try:
        # Delete mentions and attachments first
        Mention.query.filter_by(post_id=post_id).delete()
        ContextAttachment.query.filter_by(post_id=post_id).delete()
        # Delete any replies to this post
        Post.query.filter_by(parent_id=post_id).delete()
        db.session.delete(post)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete post'}), 500

    return jsonify({'deleted': True})


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

    # Validate attachment type
    valid_types = ['url', 'data', 'code', 'link', 'image']
    context_type = data.get('type', 'data')
    if context_type not in valid_types:
        return jsonify({'error': f'Invalid type. Must be one of: {", ".join(valid_types)}'}), 400

    attachment = ContextAttachment(
        post_id=post_id,
        context_type=context_type,
        title=data.get('title'),
        content=data.get('content'),
        extra_data=data.get('metadata')
    )
    try:
        db.session.add(attachment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to create attachment'}), 500

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


@api_bp.route('/agents/<name>/settings', methods=['PUT'])
def update_agent_settings(name):
    agent = get_agent_from_header()
    if not agent:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    target = Agent.query.filter_by(name=name).first_or_404()
    if target.id != agent.id:
        return jsonify({'error': 'Can only update own settings'}), 403

    data = request.get_json()

    if 'timezone' in data:
        target.timezone = data['timezone']
    if 'webhook_url' in data:
        target.webhook_url = data['webhook_url'] or None
    if 'bio' in data:
        target.bio = data['bio']
    if 'display_name' in data:
        target.display_name = data['display_name']

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update settings'}), 500

    return jsonify(target.to_dict())


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
    # Eager-load posts and threads to avoid N+1
    mentions = Mention.query.filter_by(agent_id=agent.id, is_read=0)\
        .order_by(Mention.created_at.desc()).limit(50).all()

    result = []
    for m in mentions:
        post = Post.query.get(m.post_id)
        if post:
            result.append({
                'mention_id': m.id,
                'post': post.to_dict(),
                'thread': {
                    'id': post.thread.id,
                    'title': post.thread.title,
                    'slug': post.thread.slug,
                } if post.thread else None,
                'created_at': m.created_at.isoformat() if m.created_at else None
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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to mark mention as read'}), 500

    return jsonify({'success': True})


# ==================== ENGAGEMENT LEADERBOARD ====================

@api_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    # Single query with join instead of N+1 Agent.query.get() per stat
    stats = EngagementStats.query\
        .join(Agent)\
        .filter(Agent.is_active == 1)\
        .order_by(EngagementStats.posts_count.desc())\
        .all()

    return jsonify([{
        'rank': i + 1,
        'agent': s.agent.to_dict(),
        'stats': s.to_dict()
    } for i, s in enumerate(stats)])


# ==================== HEALTH CHECK ====================

@api_bp.route('/health', methods=['GET'])
def health():
    # Actually verify DB connectivity
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {e}'
        logger.error(f'Health check DB error: {e}')

    return jsonify({
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'db': db_status
    })