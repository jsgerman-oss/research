package approval

import (
	"context"

	"github.com/auditidentity/blackrim.dev/internal/bd"
)

// BdClientAdapter wraps internal/bd.Client to satisfy the approval BDClient
// interface. Keeps the approval package free of a hard dependency on
// internal/bd while allowing production code to use the real client.
type BdClientAdapter struct {
	Client *bd.Client
}

// NewBDAdapter creates a BDClient-satisfying adapter over *bd.Client.
func NewBDAdapter(c *bd.Client) *BdClientAdapter {
	return &BdClientAdapter{Client: c}
}

// Create creates an issue and returns its ID.
func (a *BdClientAdapter) Create(ctx context.Context, title, description, issueType string, priority int) (string, error) {
	iss, err := a.Client.Create(ctx, title, description, issueType, priority)
	if err != nil {
		return "", err
	}
	return iss.ID, nil
}

// Show retrieves an issue by ID, mapping to the approval.Issue shape.
func (a *BdClientAdapter) Show(ctx context.Context, id string) (*Issue, error) {
	iss, err := a.Client.Show(ctx, id)
	if err != nil {
		return nil, err
	}
	if iss == nil {
		return nil, nil
	}
	return &Issue{
		ID:          iss.ID,
		Title:       iss.Title,
		Description: iss.Description,
		Status:      iss.Status,
		Priority:    iss.Priority,
		Labels:      iss.Labels,
		// bd.Client doesn't expose close_reason today; we read it from notes
		// or fall back to empty. For now, Notes carries decision text.
		CloseReason: iss.CloseReason,
	}, nil
}

// ListOpen returns all open issues (the approval queue filters by title).
func (a *BdClientAdapter) ListOpen(ctx context.Context) ([]Issue, error) {
	issues, err := a.Client.ListIssues(ctx, "open")
	if err != nil {
		return nil, err
	}
	out := make([]Issue, 0, len(issues))
	for _, iss := range issues {
		out = append(out, Issue{
			ID:          iss.ID,
			Title:       iss.Title,
			Description: iss.Description,
			Status:      iss.Status,
			Priority:    iss.Priority,
			Labels:      iss.Labels,
			CloseReason: iss.CloseReason,
		})
	}
	return out, nil
}

// CloseIssue closes an issue with the given reason encoded as notes.
func (a *BdClientAdapter) CloseIssue(ctx context.Context, id, reason string) error {
	return a.Client.CloseIssue(ctx, id, reason)
}
