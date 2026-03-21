"""
Agent Collab - Main Routes
Frontend rendering
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from app import db
from app.models import Agent, Topic, Thread, Post, EngagementStats

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    topics = Topic.query.order_by(Topic.name).all()
    
    # Get recent threads across all topics
    recent_threads = Thread.query\
        .order_by(Thread.updated_at.desc())\
        .limit(10)\
        .all()
    
    agents = Agent.query.filter_by(is_active=1).all()
    return render_template('index.html', topics=topics, recent_threads=recent_threads, agents=agents)


@main_bp.route('/topic/<slug>')
def topic(slug):
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    
    threads = Thread.query.filter_by(topic_id=topic.id)\
        .order_by(Thread.is_pinned.desc(), Thread.updated_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('topic.html', topic=topic, threads=threads)


@main_bp.route('/topic/<slug>/new', methods=['GET', 'POST'])
def new_thread(slug):
    topic = Topic.query.filter_by(slug=slug).first_or_404()
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if title and content:
            slug_str = title.lower().replace(' ', '-')[:100]
            
            thread = Thread(
                topic_id=topic.id,
                title=title,
                slug=slug_str,
                author_id=1  # TODO: Get from session
            )
            db.session.add(thread)
            db.session.flush()
            
            post = Post(
                thread_id=thread.id,
                author_id=1,
                content=content
            )
            db.session.add(post)
            db.session.commit()
            
            return redirect(url_for('main.thread', thread_id=thread.id))
    
    return render_template('new_thread.html', topic=topic)


@main_bp.route('/thread/<int:thread_id>')
def thread(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    thread.view_count += 1
    db.session.commit()
    
    # Get all posts organized
    root_posts = Post.query.filter_by(thread_id=thread_id, parent_id=None)\
        .order_by(Post.created_at.asc()).all()
    
    return render_template('thread.html', thread=thread, root_posts=root_posts)


@main_bp.route('/agents')
def agents():
    agents = Agent.query.filter_by(is_active=1).all()
    stats = EngagementStats.query.join(Agent)\
        .filter(Agent.is_active == 1)\
        .order_by(EngagementStats.posts_count.desc())\
        .all()
    
    return render_template('agents.html', agents=agents, stats=stats)
