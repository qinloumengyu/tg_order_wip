from django.template.response import TemplateResponse
from django.template.loader import render_to_string
from django.db.models import Q
from erp_configs import configs
from mesy import models as dbmodels
import datetime, erpapputils, html_table_to_excel, calendar

MAX_DAYS = 7

def do_trigger_positive(request, crondef, parampath):
    '''
    trigger positive command

    @param crondef :    model.RP_RULE_CRON
    '''
    vcons = configs.get_values_values(request, ['PNAME_A', 'PNAME_B', 'PNAME_C', 'FLOW__REMARKS'])
    stdstep = dbmodels.STA_STEP.objects.filter(Available=True, company=crondef.company)
    stdstepls = list(stdstep.values('id', 'Name'))
    table_len = len(stdstepls)

    request_form = request.REQUEST

    try:
        tydate = erpapputils.convert_datetimestr2dt(request_form.get('tydate', ''))
    except Exception, e:
        tydate = datetime.datetime.today()
    
    tydate_year = tydate.year 
    tydate_month = tydate.month
    monthrange = calendar.monthrange(tydate.year,tydate.month)

    if tydate_year != datetime.datetime.today().year or tydate_month != datetime.datetime.today().month:
        tydate = datetime.datetime(year = tydate_year, month = tydate_month, day = monthrange[1])

    firstDay = datetime.datetime(year = tydate_year, month = tydate_month, day = 1)
   
    sdate = tydate - datetime.timedelta(days=1)
    edate = tydate + datetime.timedelta(days=1)

    datelength = (edate-sdate).days   

    # showcontent
    showcontent = int(request_form.get('showcontent', 0))

    sum_t = [[0,0,0,0] for i in range(table_len)]
    sum_quantity = 0

    subobj = {
        'stdstepls': stdstepls,
        'request_form': request_form,
        'showcontent': showcontent,
        'tydate': tydate,
        'vcons': vcons
    }

    if parampath in ['search', 'searchandprint', 'searchexcel']:
        # steps
        stepids = [int(x) for x in request_form.getlist('steps')]
        flowins = dbmodels.FLOWINX.objects.filter(Available=True, company=request.user.company,
            Out__ReworkIn__isnull=True, Inner__Available=True).order_by('Create_date')
        if stepids:
            flowins = flowins.filter(Out__Plan_step__id__in=stepids)

        ordername = request_form['ordername'].strip()
        if ordername:
            flowins = flowins.filter(Inner__Order_drawing__Order__OrderName__icontains=ordername)
        flowins = flowins.exclude(Inner__Order_drawing__Order__isnull=True) 
 
        product = request_form['product'].strip()
        if product:
            flowins = flowins.filter(Q(Inner__Drawing__DrawingName__icontains=product) | Q(Inner__Drawing__Dn_a__icontains=product) | Q(Inner__Drawing__Dn_b__icontains=product) | Q(Inner__Drawing__Dn_c__icontains=product))

        # more or less
        flowins = flowins.exclude(Inner__Complete_date__lt=firstDay)
        flowins = flowins.exclude(Inner__Complete_date__gt=tydate)

        fils = list(flowins.values('id', 'Inner', 'Inner__DrawingNO', 'Inner__Remark', 'To_type', 'Inner__Order_drawing__Quantity','Inner__Order_drawing__Order__OrderName',
            'Inner__Drawing__DrawingName', 'Inner__Drawing__Dn_a', 'Inner__Drawing__Dn_b', 'Inner__Drawing__Dn_c',
            'Create_date', 'Quantity', 'Out__Plan_step', 'Out__Plan_step__Name'))

        myrange = [
            sdate.day
        ]
        for i in range(datelength):
            myrange.append((sdate + datetime.timedelta(days=i+1)).day)

        # hide drawings
        bhideno = 'bhideno' in request_form

        # total
        tt_cq = [0 for j in range(datelength + 1)]

        # inners
        innerdict = {}
        for f in fils:
            finner = f['Inner']
            if finner not in innerdict:
                innerdict[finner] = {
                    'Inner': f['Inner'],
                    'DrawingNO': f['Inner__DrawingNO'],
                    'Remark': f['Inner__Remark'],
                    'Order__Name': f['Inner__Order_drawing__Order__OrderName'],
                    'Drawing__DrawingName': f['Inner__Drawing__DrawingName'],
                    'Drawing__Dn_a': f['Inner__Drawing__Dn_a'],
                    'Drawing__Dn_b': f['Inner__Drawing__Dn_b'],
                    'Drawing__Dn_c': f['Inner__Drawing__Dn_c'],
                    'Create_date': f['Create_date'],
                    'Order_drawing__Quantity': f['Inner__Order_drawing__Quantity'],
                    'table': [[0,0,0,0] for i in range(table_len)],
                    'ssd': {},
                    'ssdlen': 0,
                }

            i = innerdict[finner]
            ssd = i['ssd']

            sskey = (f['Out__Plan_step'], f['Out__Plan_step__Name'])
            if sskey not in ssd:
                ssd[sskey] = {
                    'step': '',
                    'endtime': '',
                    'position': 0,
                    'lastcount': 0,
                    'nowcount': 0,
                    'cq': [0 for j in range(datelength + 1)],
                    'ng': [0 for j in range(datelength + 1)],
                    're': [0 for j in range(datelength + 1)],
                }
                i['ssdlen'] = len(ssd)

            mm = ssd[sskey]
            if f['Create_date'] < sdate:
                mm['lastcount'] += f['Quantity']
            elif f['Create_date'] < edate:
                cd = f['Create_date']
                myidx = myrange.index(cd.day)
                if myidx:
                    if f['To_type'] == dbmodels.FIN_NG:
                        mm['ng'][myidx] += f['Quantity']
                    elif f['To_type'] == dbmodels.FIN_RE:
                        mm['re'][myidx] += f['Quantity']
                    else:
                        mm['cq'][myidx] += f['Quantity']
                        tt_cq[myidx] += f['Quantity']
            mm['step'] = f['Out__Plan_step__Name']
            mm['lastcount'] = mm['lastcount'] + mm['cq'][0]
            mm['nowcount'] = mm['cq'][1]
            mm['endtime'] = f['Create_date']
            set_position(tydate,innerdict[finner],mm,stdstepls,table_len)

            if bhideno:
                mm['bhide'] = mm['lastcount'] == mm['nowcount']

        subobj['content'] = sorted(innerdict.values(), lambda x,y: cmp(x['Drawing__DrawingName'], y['Drawing__DrawingName']))
        subobj['range'] = myrange
        subobj['edate'] = edate
        subobj['stepids'] = stepids
        subobj['tt_cq'] = tt_cq

        for x in range(table_len):
            for y in subobj['content']:
                sum_t[x][0] += y['table'][x][0]
                sum_t[x][1] += y['table'][x][1]
                sum_t[x][2] += y['table'][x][2]
        subobj['sum_t'] = sum_t
        for y in subobj['content']:
            sum_quantity += y['Order_drawing__Quantity']
        subobj['sum_quantity'] = sum_quantity

        # show, change cq
        if showcontent == 1:
            for x in subobj['content']:
                for y in x['ssd'].values():
                    for j in range(datelength + 1):
                        q = y['cq'][j]
                        n = y['ng'][j]
                        r = y['re'][j]
                        if q + n + r > 0:
                            y['cq'][j] = '{}%'.format(round(q/(q+n+r), 4)*100)

        if parampath == 'search':
            return subobj
        elif parampath == 'searchexcel':
            table_str = render_to_string('tg_order_wip/single_table.html', {
                'cc': subobj
            })
            return html_table_to_excel.export_to_xls(table_str, True)
        else:
            return TemplateResponse(request, 'tg_order_wip/single_printable.html', {
                'cc': subobj
            })

    return subobj

def set_position(tydate,inner,mm, stdstepls,table_len):

    #i = 0
    j = 0
    k = -1
    for step in stdstepls:
        if(step.get('Name') == mm['step']):
            mm['position'] = j
            inner['table'][j][0] = mm['nowcount']
            inner['table'][j][1] = mm['nowcount'] + mm['lastcount']
            inner['table'][j][3] = mm['endtime']
        j += 1

    for i in range(table_len):
        if inner['table'][i][1] != 0:
            if i == 0:
                inner['table'][i][2] = inner['table'][i][1] - inner['Order_drawing__Quantity']
            else:
                for t in range(i)[::-1]:
                    if inner['table'][t][1] != 0:
                        inner['table'][i][2] = inner['table'][i][1] - inner['table'][t][1]
                        k = 1
                        break
                if k == -1:
                    inner['table'][i][2] = inner['table'][i][1] - inner['Order_drawing__Quantity']

