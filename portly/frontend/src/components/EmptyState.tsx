import React from 'react';

interface EmptyStateProps {
  message?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  message = 'No listening ports or applications found matching current filters.',
}) => (
  <div className="portly-empty-state">
    <div className="portly-empty-state-title">Nothing to show</div>
    <div className="portly-empty-state-hint">{message}</div>
  </div>
);
