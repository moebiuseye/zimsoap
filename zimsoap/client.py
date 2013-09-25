#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This client has two usages:
#
#   - Fire SOAP methods (they are "CamelCameNames()" and end with 'Request'):
#     they bind directly to sending the same-name message to the SOAP
#     server. They return XML.
#
#   - Fire high-level methods (they are "pythonic_method_names()"), they return
#     Python objects/list (see zobjects submodule for zimbra-specific Classes).
#

from os.path import dirname, abspath, join
import datetime

import pysimplesoap

import utils
import zobjects

class ShouldAuthenticateFirst(Exception):
    """ Error fired when an operation requiring auth is intented before the auth
    is done.
    """
    pass

class ZimbraAdminClient(pysimplesoap.client.SoapClient):
    """ Specialized Soap client to access zimbraAdmin webservice, handling auth.

    API ref is
    http://files.zimbra.com/docs/soap_api/8.0.4/soap-docs-804/api-reference/zimbraAdmin/service-summary.html
    """
    def __init__(self, server_host, server_port='7071',
                 *args, **kwargs):
        loc = "https://%s:%s/service/admin/soap" % (server_host, server_port)
        super(ZimbraAdminClient, self).__init__(
            location = loc,
            action = loc,
            namespace = 'urn:zimbraAdmin',
            *args, **kwargs)

        self._session = ZimbraAPISession(self)

    def login(self, admin_user, admin_password):
        self._session.login(admin_user, admin_password)
        self['context'] = self._session.get_context_header()

    def get_all_domains(self):
        obj_domains = []
        xml_doms = utils.extractResponses(self.GetAllDomainsRequest())
        return [zobjects.Domain.from_xml(d) for d in xml_doms]

    def get_mailbox_stats(self):
        """ Get global stats about mailboxes

        Parses <stats numMboxes="6" totalSize="141077"/>

        @returns dict with stats
        """
        resp = utils.extractSingleResponse(self.GetMailboxStatsRequest())
        ret = {}
        for k,v in resp.attributes().items():
            ret[k] = int(v)

        return ret

    def count_account(self, domain):
        """ Count the number of accounts for a given domain, sorted by cos

        @returns a list of pairs <ClassOfService object>,count
        """
        selector = domain.to_xml_selector()
        resp = self.CountAccountRequest(self, utils.wrap_el(selector))
        cos_list = utils.extractResponses(resp)

        ret = []

        for i in cos_list:
            ret.append( ( zobjects.ClassOfService.from_xml(i), int(i) ) )

        return list(ret)


    def get_all_mailboxes(self):
        resp = self.GetAllMailboxesRequest()
        xml_mailboxes = utils.extractResponses(resp)
        return [zobjects.Mailbox.from_xml(i) for i in xml_mailboxes]

    def get_account_mailbox(self, account_id):
        """ Returns a Mailbox corresponding to an account. Usefull to get the
        size (attribute 's'), and the mailbox ID, returns nothing appart from
        that.
        """
        selector = zobjects.Mailbox(id=account_id).to_xml_selector()
        resp = self.GetMailboxRequest(self, utils.wrap_el(selector))

        xml_mbox = utils.extractSingleResponse(resp)
        return zobjects.Mailbox.from_xml(xml_mbox)

    def get_distribution_list(self, dl_description):
        """
        @param   dl_description : a DistributionList specifying either :
                   - id:   the account_id
                   - name: the name of the list
        @returns the DistributionList
        """
        selector = dl_description.to_xml_selector()

        resp = self.GetDistributionListRequest(self, utils.wrap_el(selector))
        dl = zobjects.DistributionList.from_xml(
            utils.extractSingleResponse(resp))
        return dl

    def create_distribution_list(self, name, dynamic=0):
        resp = self.CreateDistributionListRequest(attributes={
                'name'   : name,
                'dynamic': str(dynamic)
                })

        return zobjects.DistributionList.from_xml(
            utils.extractSingleResponse(resp))


    def delete_distribution_list(self, dl):
        try:
            dl_id = dl.id

        except AttributeError:
            # No id is known, so we have to fetch the dl first
            try:
                dl_id = self.get_distribution_list(dl).id
            except AttributeError:
                raise ValueError('Unqualified DistributionList')

        self.DeleteDistributionListRequest(attributes={'id': dl_id})



class ZimbraAPISession:
    """Handle the login, the session expiration and the generation of the
       authentification header.
    """
    def __init__(self, client):
        self.client = client
        self.authToken = None

    def login(self, username, password):
        """ Performs the login agains zimbra
        (sends AuthRequest, receives AuthResponse).
        """
        response = self.client.AuthRequest(name=username, password=password)
        self.authToken, lifetime = utils.extractResponses(response)
        lifetime = int(lifetime)
        self.authToken = str(self.authToken)
        self.end_date = (datetime.datetime.now() +
                         datetime.timedelta(0, lifetime))

    def get_context_header(self):
        """ Builds the XML <context> element to be tied to SOAP requests. It
        contains the authentication string (authToken).

        @return the context as a pysimplesoap.client.SimpleXMLElement
        """

        if not self.is_logged_in():
            raise ShouldAuthenticateFirst

        context = pysimplesoap.client.SimpleXMLElement("<context/>")
        context['xmlns'] = "urn:zimbra"
        context.authToken = self.authToken
        context.authToken['xsi:type'] = "xsd:string"
        context.add_child('sessionId')
        context.sessionId['xsi:null'] = "1"

        return context

    def is_logged_in(self):
        if not self.authToken:
            return False
        return self.end_date >= datetime.datetime.now()


