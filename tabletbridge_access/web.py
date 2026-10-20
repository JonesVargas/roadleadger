from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q,Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from audit.models import AuditEvent
from .models import AccessGrant, ProductDemand,DemandItem
from .forms import GrantForm, DemandForm, DemandItems
from .service import decision

manager_required = user_passes_test(lambda u:u.is_authenticated and u.is_active and u.is_superuser)
STATE_LABELS={'authorized':'Liberado','account_inactive':'Conta inativa',
    'product_not_authorized':'Sem autorização TabletBridge','access_not_released':'Aguardando liberação',
    'access_expired':'Acesso vencido','access_revoked':'Bloqueado'}


@manager_required
def manager(request, demand_id=None):
    demand=get_object_or_404(ProductDemand,pk=demand_id) if demand_id else ProductDemand(created_by=request.user)
    form=DemandForm(request.POST or None,instance=demand,prefix='demand')
    items=DemandItems(request.POST or None,instance=demand,prefix='items')
    if request.method=='POST' and form.is_valid() and items.is_valid():
        with transaction.atomic():
            demand=form.save()
            items.instance=demand
            items.save()
            AuditEvent.objects.create(actor=request.user,action='tabletbridge.demand.saved',target=str(demand.pk),
                                      metadata={'status':demand.status})
        messages.success(request,'Demanda salva. Publicadas ficam visíveis a todos os players autorizados. Nenhuma venda foi executada.')
        return redirect('tabletbridge-manager')
    query=request.GET.get('q','').strip()[:150]
    users=get_user_model().objects.order_by('full_name','pk')
    if query: users=users.filter(Q(full_name__icontains=query)|Q(email__icontains=query))
    page=Paginator(users,10).get_page(request.GET.get('players_page'))
    players=[]
    for user in page:
        grant=AccessGrant.objects.filter(user=user).first()
        players.append({'user':user,'state':STATE_LABELS[decision(user)[0]], 'form':GrantForm(instance=grant,prefix=f'access-{user.pk}')})
    demands=Paginator(ProductDemand.objects.prefetch_related('items'),10).get_page(request.GET.get('demands_page'))
    return render(request,'tabletbridge_access/manager.html',{'demand':demand,'demand_form':form,'items':items,
        'players':players,'players_page':page,'query':query,'demands':demands})


@manager_required
@require_POST
def grant_access(request,user_id):
    user=get_object_or_404(get_user_model(),pk=user_id)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        grant=AccessGrant.objects.filter(user=user).first()
        form=GrantForm(request.POST,instance=grant,prefix=f'access-{user.pk}')
        if form.is_valid():
            obj=form.save(commit=False);obj.user=user;obj.save()
            AuditEvent.objects.create(actor=request.user,action='tabletbridge.access.changed',target=str(user.pk),
                metadata={'approved':obj.approved,'blocked':obj.blocked,
                          'expires_at':obj.expires_at.isoformat() if obj.expires_at else None})
            messages.success(request,'Acesso TabletBridge atualizado. Os planos ETS2/ATS permanecem independentes.')
        else: messages.error(request,'Liberação não salva. Confira a data e os campos informados.')
    return redirect('tabletbridge-manager')


@login_required
def demands(request):
    if decision(request.user)[0]!='authorized':
        return HttpResponseForbidden('O acesso específico ao TabletBridge não está liberado para esta conta.')
    page=Paginator(ProductDemand.objects.filter(status='published').prefetch_related(Prefetch('items',queryset=DemandItem.with_progress())),10).get_page(request.GET.get('page'))
    return render(request,'tabletbridge_access/demands.html',{'demands':page})
