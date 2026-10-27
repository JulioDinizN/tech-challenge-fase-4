package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/oracle/oci-go-sdk/v65/common"
	"github.com/oracle/oci-go-sdk/v65/common/auth"
	"github.com/oracle/oci-go-sdk/v65/queue"
)

type OCIQueuePublisher struct {
	client  queue.QueueClient
	queueID string
}

func newAnalyticsEventPublisherFromEnv() (AnalyticsEventPublisher, error) {
	queueID := strings.TrimSpace(os.Getenv("OCI_QUEUE_OCID"))
	if queueID == "" {
		return nil, nil
	}

	messagesEndpoint := strings.TrimSpace(os.Getenv("OCI_QUEUE_MESSAGES_ENDPOINT"))
	if messagesEndpoint == "" {
		return nil, fmt.Errorf("OCI_QUEUE_MESSAGES_ENDPOINT deve ser definida quando OCI_QUEUE_OCID estiver configurada")
	}

	provider, err := newOCIConfigurationProvider(strings.TrimSpace(os.Getenv("OCI_AUTH_MODE")))
	if err != nil {
		return nil, err
	}

	client, err := queue.NewQueueClientWithConfigurationProvider(provider)
	if err != nil {
		return nil, fmt.Errorf("criar cliente OCI Queue: %w", err)
	}
	client.Host = strings.TrimRight(messagesEndpoint, "/")

	return &OCIQueuePublisher{
		client:  client,
		queueID: queueID,
	}, nil
}

func newOCIConfigurationProvider(authMode string) (common.ConfigurationProvider, error) {
	if authMode == "" {
		authMode = "workload_identity"
	}

	switch authMode {
	case "workload_identity":
		provider, err := auth.OkeWorkloadIdentityConfigurationProvider()
		if err != nil {
			return nil, fmt.Errorf("configurar OKE workload identity: %w", err)
		}
		return provider, nil
	case "instance_principal":
		provider, err := auth.InstancePrincipalConfigurationProvider()
		if err != nil {
			return nil, fmt.Errorf("configurar instance principal: %w", err)
		}
		return provider, nil
	case "config_file":
		configFile := strings.TrimSpace(os.Getenv("OCI_CONFIG_FILE"))
		if configFile == "" {
			home, err := os.UserHomeDir()
			if err != nil {
				return nil, fmt.Errorf("localizar diretório do usuário: %w", err)
			}
			configFile = filepath.Join(home, ".oci", "config")
		}

		profile := strings.TrimSpace(os.Getenv("OCI_CONFIG_PROFILE"))
		if profile == "" {
			profile = "DEFAULT"
		}
		return common.CustomProfileConfigProvider(configFile, profile), nil
	default:
		return nil, fmt.Errorf("OCI_AUTH_MODE inválido %q; use workload_identity, instance_principal ou config_file", authMode)
	}
}

func (p *OCIQueuePublisher) Publish(ctx context.Context, content string) error {
	request := queue.PutMessagesRequest{
		QueueId: common.String(p.queueID),
		PutMessagesDetails: queue.PutMessagesDetails{
			Messages: []queue.PutMessagesDetailsEntry{
				{Content: common.String(content)},
			},
		},
	}

	if _, err := p.client.PutMessages(ctx, request); err != nil {
		return fmt.Errorf("publicar mensagem: %w", err)
	}
	return nil
}
