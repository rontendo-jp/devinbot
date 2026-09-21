'use client';

import { useState, useEffect } from 'react';
import { config } from '@/config';

interface Repository {
  id: string;
  github_repo_path: string;
  telegram_chat_id: string;
  enabled: boolean;
}

interface RepositorySelectorProps {
  selectedRepository: string | null;
  onSelectRepository: (repoId: string | null) => void;
}

export default function RepositorySelector({ 
  selectedRepository, 
  onSelectRepository
}: RepositorySelectorProps) {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    fetchRepositories();
  }, []);

  const fetchRepositories = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${config.apiUrl}/api/repositories/`);
      if (!response.ok) throw new Error('Failed to fetch repositories');
      
      const data = await response.json();
      setRepositories(data.repositories);
    } catch (err) {
      console.error('Error fetching repositories:', err);
    } finally {
      setLoading(false);
    }
  };

  const selectedRepo = repositories.find(r => r.id === selectedRepository);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="min-w-[200px] px-4 py-2 bg-white border border-gray-300 rounded-lg text-left hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={loading}
      >
        {loading ? (
          <span className="text-gray-500">Loading...</span>
        ) : selectedRepo ? (
          <span className="text-gray-900">{selectedRepo.github_repo_path}</span>
        ) : (
          <span className="text-gray-500">All Repositories</span>
        )}
      </button>

      {isOpen && (
        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-auto">
          <button
            onClick={() => {
              onSelectRepository(null);
              setIsOpen(false);
            }}
            className={`w-full px-4 py-2 text-left hover:bg-gray-50 ${
              !selectedRepository ? 'bg-blue-50 text-blue-900' : 'text-gray-900'
            }`}
          >
            All Repositories
          </button>
          {repositories.map((repo) => (
            <button
              key={repo.id}
              onClick={() => {
                onSelectRepository(repo.id);
                setIsOpen(false);
              }}
              className={`w-full px-4 py-2 text-left hover:bg-gray-50 ${
                selectedRepository === repo.id ? 'bg-blue-50 text-blue-900' : 'text-gray-900'
              }`}
            >
              {repo.github_repo_path}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}