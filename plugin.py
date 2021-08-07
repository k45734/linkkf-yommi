# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import sys
import traceback
import json

# third-party
from flask import Blueprint, request, Response, render_template, redirect, jsonify, url_for, send_from_directory
from flask_login import login_required
from flask_socketio import SocketIO, emit, send

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, socketio, path_app_root
from framework.util import Util, AlchemyEncoder
from system.logic import SystemLogic

# 패키지

from .logic import Logic
from .logic_linkkfyommi import LogicLinkkfYommi
from .logic_queue import QueueEntity, LogicQueue
from .model import ModelSetting
# blueprint = Blueprint(package_name,
#                       package_name,
#                       url_prefix='/%s' % package_name,
#                       template_folder=os.path.join(os.path.dirname(__file__),
#                                                    'templates'))

package_name = __name__.split('.')[0]
logger = get_logger(package_name)

#########################################################
# 플러그인 공용
#########################################################
blueprint = Blueprint(package_name, package_name, url_prefix='/%s' % package_name,
                      template_folder=os.path.join(
                          os.path.dirname(__file__), 'templates'),
                      static_folder=os.path.join(os.path.dirname(__file__), 'static'))


# def plugin_load():
#     Logic.plugin_load()


# def plugin_unload():
#     Logic.plugin_unload()

# 메뉴 구성.
menu = {
    'main': [package_name, 'linkkf-yommi'],
    'sub': [['setting', '설정'], ['request', '요청'], ['queue', '큐'],
            ['log', '로그']],
    'category': 'vod',
}

plugin_info = {
    'version': '0.1.4.0',
    'name': 'linkkf-yommi 다운로드',
    'category_name': 'vod',
    'icon': '',
    'developer': 'projectdx && persuade',
    'description': 'linkkf 사이트에서 애니 다운로드',
    'home': 'http://yommi.duckdns.org:30000/yommi/linkkf-yommi',
    'more': '',
}
#########################################################


def plugin_load():
    Logic.plugin_load()
    LogicQueue.queue_load()


def plugin_unload():
    Logic.plugin_unload()

#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/setting' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    if sub == 'setting':
        setting_list = db.session.query(ModelSetting).all()
        arg = Util.db_list_to_dict(setting_list)
        arg['scheduler'] = str(scheduler.is_include(package_name))
        arg['is_running'] = str(scheduler.is_running(package_name))
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub in ['request', 'queue', 'list']:
        setting_list = db.session.query(ModelSetting).all()
        arg = Util.db_list_to_dict(setting_list)
        arg['current_code'] = LogicLinkkfYommi.current_data[
            'code'] if LogicLinkkfYommi.current_data is not None else None
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html',
                           title='%s - %s' % (package_name, sub))


#########################################################
# For UI (보통 웹에서 요청하는 정보에 대한 결과를 리턴한다.)
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
def ajax(sub):
    logger.debug('AJAX %s %s', package_name, sub)
    if sub == 'setting_save':
        try:
            ret = Logic.setting_save(request)
            return jsonify(ret)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    # 요청
    elif sub == 'analysis':
        try:
            code = request.form['code']
            data = LogicLinkkfYommi.get_title_info(code)

            logger.info(type(data))
            logger.info(data)
            # logger.info(data.decode('utf-8'))
            # retData = json.dumps(data).encode("utf-8")
            # json_string = json.dumps(data, ensure_ascii=False)
            #creating a Response object to set the content type and the encoding
            # retData = Response(
            # json_string, content_type="application/json; charset=utf-8")
    # return response

            # return jsonify(ret)
            # return retData
            return jsonify(data)
            # return jsonify({'ret': 'success', 'data': retData})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'apply_new_title':
        try:
            new_title = request.form['new_title']
            ret = LogicLinkkfYommi.apply_new_title(new_title)
            return jsonify(ret)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'apply_new_season':
        try:
            new_season = request.form['new_season']
            ret = LogicLinkkfYommi.apply_new_season(new_season)
            return jsonify(ret)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'add_whitelist':
        try:
            ret = LogicLinkkfYommi.add_whitelist()
            return jsonify(ret)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'add_queue':
        try:
            ret = {}
            code = request.form['code']
            info = LogicLinkkfYommi.get_info_by_code(code)
            if info is not None:
                from .logic_queue import LogicQueue
                tmp = LogicQueue.add_queue(info)
                ret['ret'] = 'success' if tmp else 'fail'
            else:
                ret['ret'] = 'no_data'
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'fail'
            ret['log'] = str(e)
        return jsonify(ret)
    elif sub == 'add_queue_checked_list':
        try:
            from .logic_queue import LogicQueue
            ret = {}
            code = request.form['code']
            code_list = code.split(',')
            count = 0
            for c in code_list:
                info = LogicLinkkfYommi.get_info_by_code(c)
                if info is not None:
                    tmp = LogicQueue.add_queue(info)
                    count += 1
            ret['ret'] = 'success'
            ret['log'] = count
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'fail'
            ret['log'] = str(e)
        return jsonify(ret)

    # 큐
    elif sub == 'program_auto_command':
        try:
            from .logic_queue import LogicQueue
            ret = LogicQueue.program_auto_command(request)
            return jsonify(ret)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
def api(sub):
    logger.debug('api %s %s', package_name, sub)


#########################################################
# socketio
#########################################################
sid_list = []


@socketio.on('connect', namespace='/%s' % package_name)
def connect():
    try:
        sid_list.append(request.sid)
        tmp = None
        from .logic_queue import QueueEntity
        data = [_.__dict__ for _ in QueueEntity.entity_list]
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        emit('on_connect', tmp, namespace='/%s' % package_name)
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


@socketio.on('disconnect', namespace='/%s' % package_name)
def disconnect():
    try:
        sid_list.remove(request.sid)
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


def socketio_callback(cmd, data):
    if sid_list:
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        socketio.emit(cmd, tmp, namespace='/%s' % package_name, broadcast=True)


def socketio_list_refresh():
    data = [_.__dict__ for _ in QueueEntity.entity_list]
    tmp = json.dumps(data, cls=AlchemyEncoder)
    tmp = json.loads(tmp)
    socketio_callback('list_refresh', tmp)